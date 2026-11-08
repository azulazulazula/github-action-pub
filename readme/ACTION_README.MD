# GitHub Actions と承認の流れ

この文書では、ブランチ、Pull Request（PR）、GitHub Actions、Environment の関係をまとめます。

## 基本の流れ

1. `main` から作業ブランチを作ります（例: `feature/...`、`docs/...`）。
2. 変更を作業ブランチに commit して push します。
3. `main` 向けに PR を作成し、変更内容をレビューします。
4. Ruleset の条件を満たしたら PR を `main` にマージします。
5. `main` への push をトリガーに GitHub Actions が実行されます。
6. デプロイジョブが `prod` Environment を参照している場合、Required reviewers の承認後にジョブが続行します。

## PR レビュー承認とデプロイ承認

この2つは別の承認です。

- **PR レビュー承認**は、マージ前の変更確認です。Ruleset で設定します。Ruleset の対象は PR の作業元ブランチではなく、マージ先ブランチです。たとえば `main` を対象にして Required approvals を `1` にすると、`main` 向け PR に1件の承認が必要です。
- **デプロイ承認**は、デプロイジョブを開始する前の承認です。Settings → Environments で Required reviewers を設定し、ワークフローの対象ジョブで `environment: prod` のように指定します。
- `dev` Environment に Required reviewers を設定しなければ、`dev` を参照するジョブは Environment の承認待ちになりません。
- Ruleset の PR 承認設定だけなら、ワークフロー YAML の変更は不要です。Environment の承認を実際のジョブに適用するには、ジョブがその Environment を参照する必要があります。

## ワークフローのトリガー

PR の作成や更新時に処理を実行する場合は、ワークフローで `pull_request` をトリガーにします。PR が `main` にマージされた後に処理を実行する場合は、`main` への `push` をトリガーにします。

ジョブが Environment の承認待ちになるのは、そのジョブで対象 Environment を指定している場合です。PR のレビュー承認と Environment の承認は別々に設定・管理します。

## 変更を取り込むとき

`main` に Ruleset が設定されている場合、変更は作業ブランチに push して PR 経由でマージします。ドキュメントだけの変更でも同じ流れです。
