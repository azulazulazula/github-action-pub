#!/usr/bin/env bash
set -euo pipefail

RESOURCE="${1:?Usage: deploy-resource.sh <vpc|s3|ec2|ecs>}"
REGION="${AWS_REGION:-ap-south-1}"
ACCOUNT_ID="${AWS_ACCOUNT_ID:-798452926315}"

deploy_stack() {
  local template="$1"
  local stack="$2"
  shift 2

  aws cloudformation validate-template \
    --template-body "file://$template"

  aws cloudformation deploy \
    --template-file "$template" \
    --stack-name "$stack" \
    --no-fail-on-empty-changeset \
    "$@"

  aws cloudformation describe-stacks \
    --stack-name "$stack" \
    --query 'Stacks[0].Outputs' \
    --output table
}

deploy_vpc() {
  deploy_stack \
    .github/workflows/cfm/vpc/vpc.yml \
    eiei-mun-vpc-prototype
}

deploy_s3() {
  deploy_stack \
    .github/workflows/cfm/s3/s3.yml \
    eiei-mun-s3-prototype
}

deploy_ec2() {
  local vpc_id subnet_id ami_id

  vpc_id=$(aws cloudformation describe-stacks \
    --stack-name eiei-mun-vpc-prototype \
    --query "Stacks[0].Outputs[?OutputKey=='VpcId'].OutputValue | [0]" \
    --output text)
  subnet_id=$(aws cloudformation describe-stacks \
    --stack-name eiei-mun-vpc-prototype \
    --query "Stacks[0].Outputs[?OutputKey=='PublicSubnetId'].OutputValue | [0]" \
    --output text)
  test "$vpc_id" != "None"
  test "$subnet_id" != "None"

  ami_id=$(aws ec2 describe-images \
    --owners amazon \
    --filters Name=name,Values='al2023-ami-2023.*-kernel-*-arm64' \
              Name=architecture,Values=arm64 \
              Name=state,Values=available \
    --query 'sort_by(Images,&CreationDate)[-1].ImageId' \
    --output text)
  test "$ami_id" != "None"

  deploy_stack \
    .github/workflows/cfm/ec2.yml \
    eiei-mun-ec2-prototype \
    --parameter-overrides \
      AmiId="$ami_id" \
      VpcId="$vpc_id" \
      SubnetId="$subnet_id"
}

deploy_ecs() {
  local from_image from_name registry image_uri task_definition_arn

  mkdir -p build/classes
  find src/main/java -name '*.java' -print0 |
    xargs -0 javac --release 21 --add-modules jdk.httpserver -d build/classes
  jar --create --file build/hello-world.jar \
    --main-class hello.HelloWorldServer \
    -C build/classes .

  from_image=$(awk '$1 == "FROM" { image=$NF; sub(/#.*/, "", image); print image; exit }' Dockerfile)
  test -n "$from_image"
  from_name="${from_image%:*}"

  registry="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
  aws ecr get-login-password --region "$REGION" |
    docker login --username AWS --password-stdin "$registry"

  image_uri="$registry/hello-nginx:$GITHUB_SHA"
  docker build --file Dockerfile --tag "$image_uri" .
  docker push "$image_uri"

  jq --arg image "$image_uri" --arg base "$from_name" --arg revision "$GITHUB_SHA" '
    .containerDefinitions |= map(
      if .name == "hello-world" then .image = $image else . end
    )
    | .tags = (((.tags // [])
      | map(select(.key != "base-image" and .key != "source-revision")))
      + [
          {"key":"base-image","value":$base},
          {"key":"source-revision","value":$revision}
        ])
  ' .github/ecs/task-definition.json > build/task-definition.json

  task_definition_arn=$(aws ecs register-task-definition \
    --cli-input-json file://build/task-definition.json \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

  aws ecs update-service \
    --cluster hello-nginx-cluster \
    --service hello-nginx-service \
    --task-definition "$task_definition_arn" \
    --region "$REGION"

  aws ecs wait services-stable \
    --cluster hello-nginx-cluster \
    --services hello-nginx-service \
    --region "$REGION"
}

case "$RESOURCE" in
  vpc) deploy_vpc ;;
  s3) deploy_s3 ;;
  ec2) deploy_ec2 ;;
  ecs) deploy_ecs ;;
  *)
    echo "Unknown resource: $RESOURCE" >&2
    exit 2
    ;;
esac
