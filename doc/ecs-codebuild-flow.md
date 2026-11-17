# ECSイメージをCodeBuildで作る処理フロー

## 目的

既存のGitHub ActionsによるECSビルド・デプロイ方式を残したまま、別の deploy-ecs-codebuild.yml でイメージビルドをAWS CodeBuildへ移す。親の依存関係プランからは、引き続きECSリソースとして順次実行する。

## フロー

```mermaid
flowchart TD
    A[mainへの変更] --> B[親ワークフロー]
    B --> C[Pythonが差分と依存関係を解析]
    C --> D[VPCワークフロー]
    D --> E[ECS用CodeBuildワークフロー]
    E --> F[CodeBuildプロジェクトをCloudFormationで確認・更新]
    F --> G{GitHub接続がAVAILABLE?}
    G -- いいえ --> H[AWSコンソールで接続を承認]
    H --> E
    G -- はい --> I[CodeBuildをコミットSHA指定で起動]
    I --> J[JARをビルド]
    J --> K[Dockerイメージを作りECRへpush]
    K --> L[ActionsがCodeBuild成功を待つ]
    L --> M[CloudFormationでECSクラスター・タスク定義・サービスをデプロイ]
    M --> N[ECSサービス安定化を待つ]
    N --> O[Hello WorldのURLをActions実行サマリーに表示]
```

## ワークフローごとの責務

### .github/workflows/deploy-aws-resources.yml — 親ワークフロー

- 変更パスから対象リソースと前提リソースを特定する。
- .github/deploy/dependency.yml の依存順で子ワークフローを順次起動する。
- ECSの変更ではVPCを先に実行し、その後 deploy-ecs-codebuild.yml を起動する。

### .github/workflows/deploy-ecs-codebuild.yml

- prod 環境で承認を受けてAWS OIDCロールを引き受ける。
- CodeBuild用CloudFormationスタックを作成・更新する。
- GitHub接続が AVAILABLE であることを確認する。
- 対象コミットSHAを指定してCodeBuildを開始し、成功まで待つ。
- 成功後にイメージURIとコミットタグをECS CloudFormationスタックへ渡す。
- ECSが安定したら、タスクのパブリックIPを使ったURLを実行サマリーへ出す。

### CodeBuildプロジェクトと .github/ecs/buildspec.yml

- GitHub App接続を使って対象コミットを取得する。
- Java 21でJARを生成し、Dockerイメージを構築してECRへpushする。
- CodeBuildサービスロールは、対象リポジトリの読み取り、対象ECRリポジトリへのpush、専用CloudWatch Logsへの書き込みに限定する。
- CodeBuildは専用VPCに接続せず、GitHubとコンテナレジストリへの通信にNAT Gatewayを必要としない。

## 一度だけ必要なGitHub接続承認

CloudFormationで作成されるCodeConnectionsは初期状態が PENDING となる。初回のワークフローは接続状態を確認し、未承認ならAWSコンソールのConnections画面へのリンクをActionsサマリーに出して停止する。

AWSコンソールでGitHub Appを接続し、対象リポジトリだけにアクセスを許可した後、親ワークフローを再実行する。接続が AVAILABLE になればCodeBuildが続行する。

## IAM権限

- GitHub Actions用の既存ロール: CodeBuildスタック/ECSスタックのCloudFormation操作、対象CodeBuildプロジェクトの起動・状態確認、ECSサービス安定化確認に必要な権限。
- CodeBuildサービスロール: CodeConnectionsから対象GitHubリポジトリを読み取り、指定ECRリポジトリへpushし、指定CloudWatch Logsへ書き込む権限。
- タスク実行ロール: 既存のECSタスク実行ロールを使う。CodeBuild用ロールとは分離する。

## 現在の扱い

この方式は既存ワークフローとは別ファイルで追加する。依存関係定義を新しいワークフローへ切り替えた後、親ワークフローのECS実行がCodeBuild方式を使う。deploy-ecs-hello-world.yml は比較・切り戻し用に残す。
