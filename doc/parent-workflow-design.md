# 親・共通子ワークフロー設計書

## 1. 目的

プルリクエストの承認、または手動実行を入口として、変更されたAWSサービスを判定し、depend.txt に定義された依存関係と順序に従って、共通の子ワークフローをサービスごとに順次呼び出す。

現在の子ワークフローは、呼び出されたサービス名をログに表示する検証用である。将来、サービスごとのCloudFormation処理などに置き換える場合も、親側の変更検知・順序制御・共通子ワークフロー呼び出しの形を維持する。

## 2. 対象ファイル

| ファイル | 役割 |
| --- | --- |
| .github/workflows/parent.yaml | 起動条件を受け、差分判定、計画作成、順次ディスパッチを行う親ワークフロー |
| .github/workflows/childresource.yaml | サービス名とリクエストIDを入力で受け取る共通子ワークフロー |
| .github/scripts/create-resource-plan.py | depend.txt と変更ファイル一覧から対象サービスと実行順を生成する |
| depend.txt | サービス名、監視対象パス、依存サービスを宣言する |

## 3. 起動条件

### プルリクエスト承認

parent.yaml は pull_request_review の submitted イベントで起動する。ジョブは次の条件を満たす場合だけ実行する。

- レビュー結果が approved
- プルリクエストのベースブランチが main

レビューコメントや変更要求では、親ジョブは実行されない。PR作成時点では実行せず、承認を実行タイミングとする。

差分はイベントに含まれるベースSHAとPRのヘッドSHAの間で取得する。対象ブランチにはPRのベースブランチを使う。

### 手動実行

workflow_dispatch から起動する。入力 compare_to を差分比較の基準ブランチとして使い、実行中のコミットとの差分から対象サービスを決める。対象ブランチは手動実行時のブランチである。

## 4. 処理フロー

1. 親ワークフローが起動する。
2. イベント種別に応じて差分比較のベースSHA、ヘッドSHA、子ワークフローの実行ブランチを決める。
3. Gitの差分から変更ファイル一覧を作成する。
4. create-resource-plan.py が depend.txt を読み込み、監視パスに一致するサービスを選ぶ。
5. 変更されたサービスを起点に、依存するサービスを実行対象へ加える。
6. 依存関係を守り、depend.txt の記載順を保って実行順を決める。
7. 親が実行計画のサービスを先頭から1件ずつ childresource.yaml に渡し、子の完了を待ってから次のサービスを呼び出す。
8. 子ワークフローは受け取ったサービス名をログに出す。

~~~mermaid
sequenceDiagram
    actor User as 利用者
    participant GH as GitHub Actions
    participant Parent as parent.yaml
    participant Planner as create-resource-plan.py
    participant Manifest as depend.txt
    participant Child as childresource.yaml

    User->>GH: PRを承認 / 手動実行
    GH->>Parent: 起動イベント
    Parent->>Parent: 変更ファイル一覧を作成
    Parent->>Planner: manifest + 変更ファイル
    Planner->>Manifest: サービス定義を読む
    Planner-->>Parent: execution_order
    loop 実行計画の各サービスを順番に
        Parent->>Child: service_name, request_id
        Child-->>Parent: サービス名をログに表示して完了
    end
~~~

## 5. 親と子の責務

### 親ワークフロー

- 起動条件の制御
- PRまたは手動実行の差分取得
- 実行計画の生成と表示
- 共通子ワークフローの逐次呼び出し
- 子ワークフローの完了待ちと失敗の伝播

親はサービスごとの個別分岐を持たない。サービス一覧や監視パス、依存関係をワークフロー内に重複して書かず、depend.txt と計画生成プログラムを利用する。

### 共通子ワークフロー

- service_name と request_id を入力として受け取る
- 現在はサービス名をログに表示する
- 将来はサービス名に対応する処理を実行する共通の入口となる

子は親から渡された1サービスを処理する。複数サービスの並び替えは親側の計画生成で完了している。

## 6. 順次実行の意味

「順次echo」ではなく、「共通子ワークフローをサービス単位で順次呼び出す」設計である。

親は各サービス名を自身のステップで出力するだけではない。各サービスについて gh workflow run childresource.yaml 相当のディスパッチを行い、該当する子の完了後に次のサービスへ進む。現時点では子の処理内容がechoなので、子ログにサービス名が表示される。

## 7. 実行例

現在の depend.txt の設定で、S3の監視対象ファイルだけが変更された場合:

- 計画対象: S3
- 起動する子: childresource.yaml を1回
- 子のログ: S3

VPCの監視対象ファイルが変更された場合:

- 計画対象: VPC、EC2、ECS
- 実行順: depend.txt の依存関係と宣言順に従う
- 子: サービスごとに共通ワークフローを1回ずつ順番に起動

監視対象外のファイルだけが変更された場合、実行計画は空になり、子ワークフローは起動しない。

## 8. 今後の処理追加時の方針

現時点の子はechoのみで、AWSリソースの作成・更新は行わない。CloudFormationなどを実行するよう変更する場合は、共通子ワークフローの中でサービス名から対象テンプレートや処理を解決する。AWS更新を加える変更では、対象スタック、権限、入力値、失敗時の扱いを別途設計する。
