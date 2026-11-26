# Change Set 作成・承認・実行の流れ

~~~mermaid
flowchart TD
    PR[PR作成・更新] --> 判定{VPCも変更？}

    判定 -- "いいえ: EC2のみ" --> EC2事前["承認前：既存VPCの出力値を使い<br/>EC2 Change Setを作成・確認"]
    EC2事前 --> 承認1[PR承認]
    承認1 --> EC2実行1["承認後：確認済みのEC2 Change Setを実行"]

    判定 -- "はい: VPCとEC2" --> VPC事前["承認前：VPC Change Setを作成・確認<br/>EC2 Change Setはまだ作らない"]
    VPC事前 --> 承認2[PR承認]
    承認2 --> VPC実行[VPC Change Setを実行]
    VPC実行 --> 完了待ち[VPCスタックの完了を待つ]
    完了待ち --> 新出力[更新後のVPC・Subnet出力を取得]
    新出力 --> EC2事後["新しい出力値でEC2 Change Setを作成・確認"]
    EC2事後 --> 承認方法{EC2 Change Setの承認方法}
    承認方法 -- 追加承認 --> 承認3[EC2 Change Setを確認して追加承認]
    承認3 --> EC2実行2[EC2 Change Setを実行]
    承認方法 -- 追加承認なし --> EC2実行2
~~~

## EC2だけを変更する場合

承認前に、現在のVPCスタックから取得したVPC IDとSubnet IDを使ってEC2 Change Setを作成します。PR承認後は、そのChange Setを実行します。

## VPCとEC2を同じPRで変更する場合

EC2 Change Setを承認前に作成すると、実行前のVPC出力値を使う可能性があります。そのため、まず承認後にVPC Change Setを実行し、スタックの完了後に新しいVPC・Subnet出力値を取得してからEC2 Change Setを作成します。

このEC2 Change SetはPR承認時点では存在しないため、EC2の変更内容を人が確認してから実行するには追加承認が必要です。追加承認を設けない場合、EC2 Change Setは作成後に自動実行する設計になります。
