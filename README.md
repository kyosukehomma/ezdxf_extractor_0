# juudan_to_kikakouzou_ippan_extracter
縦断図dxfファイルから値を抽出して照査用のExcelファイルを作成します。

## 目次
1. 処理内容
2. 使い方
3. 注意事項
4. フォルダ構成
5. フォルダ・ファイル説明
6. エラー対応
7. 各種情報
---
---

# 1. 処理内容
1. inputフォルダ直下のdxfファイルを参照する
2. dxfファイルから各種エンティティを読み取る
3. templateフォルダ直下のExcelファイルに値を転記する
4. outputフォルダ直下にタイムスタンプ付きフォルダを作成する
5. 当該タイムスタンプ付きフォルダに処理済のExcelファイルを保存する

---
---
# 2. 使い方
## 事前準備
### 0. フォルダ構成が以下のようになっているか確認してください。
![alt text](_assets/how_to_use_0.png)

## juudan_to_kikakouzou_ippan_extracter.exe を使用する場合
### 1. inputフォルダにdxfファイルを保存します。
![alt text](_assets/how_to_use_1.png)

### 2. juudan_to_kikakouzou_ippan_extracter.exe をダブルクリックします。
![alt text](_assets/how_to_use_2.png)

### 3. Windowsディフェンダーが表示されたら「ブロックの解除」をクリックします。
![alt text](_assets/how_to_use_3.png)

### 4. ターミナルが起動して「処理確認」ウィンドウが表示されたら、「OK」をクリックします。
![alt text](_assets/how_to_use_4.png)

### 5. 「処理完了」ウィンドウが表示されたら、「OK」をクリックします。
![alt text](_assets/how_to_use_5.png)

### 6. outputフォルダで処理結果を確認します。
![alt text](_assets/how_to_use_8.png)

### 7. inputフォルダで 処理が完了したdxfファイルが、used_* フォルダに移動しているか確認します。
![alt text](_assets/how_to_use_10.png)

### 8. 処理に問題があった場合、_logsフォルダの該当処理日時のlogファイルを管理者に共有してください（詳しくは「6. エラー対応」をご参照ください）。
![alt text](_assets/how_to_use_12.png)
---
---

## juudan_to_kikakouzou_ippan_extracter.py を使用する場合

juudan_to_kikakouzou_ippan_extracter.exe の代わりに、Pythonスクリプトとして実行することができます。<br>
juudan_to_kikakouzou_ippan_extracter.py　は、<strong>tools/controller.py</strong>を編集して設定を変更することができます。

### 事前準備（初回のみ）

1. Python（バージョン3.13系）を次のWebサイトからダウンロードしてしてください。
<br>
[https://www.python.org/downloads/](https://www.python.org/downloads/)

2. ダウンロードしたインストーラを起動して、「Add Python to PATH」にチェックを入れてインストールしてください。
<br>
![alt text](_assets/how_to_set_py_0.png)
---

### セットアップ手順（初回のみ）

1. 本ツールのフォルダを開きます。

2. `00_install.bat` をダブルクリックします。
<br>
![alt text](_assets/how_to_set_py_1.png)

3. 以下のようなメッセージが表示され、セットアップが実行されます。
<br>
![alt text](_assets/how_to_set_py_2.png)

4. 「セットアップ完了」と表示されたら終了です。

※初回は数分かかる場合があります

---

### 実行方法

1. 本ツールのフォルダを開きます。

2. `01_run.bat` をダブルクリックします。
<br>
![alt text](_assets/how_to_use_py_0.png)

3. 処理確認ダイアログが表示されるので、「OK」を押して実行してください。
<br>
![alt text](_assets/how_to_use_py_1.png)
<br>
![alt text](_assets/how_to_use_py_2.png)

---
---
# 3. 注意事項

1. 帯の中におさまっていないTEXTエンティティは取得しません。
   - 例外として、"勾配" は、上にはみだすテキストエンティティは取得します。
   - MTEXT は TEXT に変換して取得します（dxfファイルでは MTEXT のまま維持）。

2. ["曲率", "片勾配すり付図", "勾配"] を取得するレイヤーは以下の通りです。
   - "D-TTL-BAND"

   ※ 01_run.bat での実行に限りますが、取得対象を追加したい場合<br>
      メモ帳などで <strong>tools/controller.py</strong>を開きます。<br>
      ![alt text](_assets/how_to_edit_01.png)
      <br>
      Ctrl + F で <strong>BAND_LAYERS</strong> を検索します。<br>
      ![alt text](_assets/how_to_edit_02.png)
      <br>
      以下のように要素を追加します。<br>
      ```
      # "D-TTR-XXXX" を追加する場合
      BAND_LAYERS: List[str] = [
         "D-TTL-BAND",
         "D-TTR-XXXX",
      ]
      ```


3. "曲率" 帯関係：
   1. "曲率" として識別できる帯タイトルは以下の通りです。
      - "曲率"
      - "曲線"
      - "曲率図"
      - "曲線図"
      - "曲率方向"
      - "曲線方向"
      - "曲", "率"　※ 2つのTEXTに分かれている
      - "曲", "線"　※ 2つのTEXTに分かれている
      - "曲", "図"　※ 2つのTEXTに分かれている
      - "曲", "向"　※ 2つのTEXTに分かれている

      ※ 01_run.bat での実行に限りますが、取得対象を追加したい場合<br>
         メモ帳などで <strong>tools/controller.py</strong>を開きます。<br>
         ![alt text](_assets/how_to_edit_01.png)
         <br>
         Ctrl + F で <strong>CURVATURE_TITLE_CANDIDATES</strong> を検索します。<br>
         ![alt text](_assets/how_to_edit_03.png)
         <br>
         以下のように要素を追加します。<br>
         ```
         ("{帯タイトル}", "{帯タイトルの取得対象とする最初の1文字}", "{帯タイトルの取得対象とする最後の1文字}"),
         ```

   2. "曲線長" として識別するTEXTは以下の通りです。
      - "L=*"
      - "L1=*"
      - "LC=*"
      - "L2=*"

      ※ 01_run.bat での実行に限りますが、取得対象を追加したい場合<br>
         メモ帳などで <strong>tools/controller.py</strong>を開きます。<br>
         ![alt text](_assets/how_to_edit_01.png)
         <br>
         Ctrl + F で <strong>CURVATURE_L_PREFIXES</strong> を検索します。<br>
         ![alt text](_assets/how_to_edit_04.png)
         <br>
         以下のように要素を追加します。<br>
         ```
         # "LX=" を追加する場合
         CURVATURE_L_PREFIXES: List[str] = [
            "L=",
            "L1=",
            "LC=",
            "L2=",
            "LX=",
         ]
         ```

   3. "曲線半径" として識別するTEXTは以下の通りです。
      - "R=*"

      ※ 01_run.bat での実行に限りますが、取得対象を追加したい場合<br>
         メモ帳などで <strong>tools/controller.py</strong>を開きます。<br>
         ![alt text](_assets/how_to_edit_01.png)
         <br>
         Ctrl + F で <strong>CURVATURE_R_PREFIXES</strong> を検索します。<br>
         ![alt text](_assets/how_to_edit_05.png)
         <br>
         以下のように要素を追加します。<br>
         ```
         # "RX=" を追加する場合
         CURVATURE_R_PREFIXES: List[str] = [
            "R=",
            "RX=",
         ]
         ```

   4. "パラメータ" として識別するTEXTは以下の通りです。
      - "A=*"

      ※ 01_run.bat での実行に限りますが、取得対象を追加したい場合<br>
         メモ帳などで <strong>tools/controller.py</strong>を開きます。<br>
         ![alt text](_assets/how_to_edit_01.png)
         <br>
         Ctrl + F で <strong>CURVATURE_A_PREFIXES</strong> を検索します。<br>
         ![alt text](_assets/how_to_edit_06.png)
         <br>
         以下のように要素を追加します。<br>
         ```
         # "AX=" を追加する場合
         CURVATURE_A_PREFIXES: List[str] = [
            "A=",
            "AX=",
         ]
         ```

4. "片勾配すり付図" 帯関係：
   1. "片勾配すり付図"として識別できる帯タイトルは以下の通りです。
      - "片勾配すり付け図"
      - "片勾配すり付図"
      - "片勾配"
      - "片", "図"　※ 2つのTEXTに分かれている
      - "片", "配"　※ 2つのTEXTに分かれている

      ※ 01_run.bat での実行に限りますが、取得対象を追加したい場合<br>
         メモ帳などで <strong>tools/controller.py</strong>を開きます。<br>
         ![alt text](_assets/how_to_edit_01.png)
         <br>
         Ctrl + F で <strong>SUPERELEVATION_TITLE_CANDIDATES</strong> を検索します。<br>
         ![alt text](_assets/how_to_edit_07.png)
         <br>
         以下のように要素を追加します。<br>
         ```
         ("{帯タイトル}", "{帯タイトルの取得対象とする最初の1文字}", "{帯タイトルの取得対象とする最後の1文字}"),
         ```

5. "勾配" 帯関係：
   1. "勾配" として識別できる帯タイトルは以下の通りです。
      - "勾配"
      - "勾", "配"　※ 2つのTEXTに分かれている

      ※ 01_run.bat での実行に限りますが、取得対象を追加したい場合<br>
         メモ帳などで <strong>tools/controller.py</strong>を開きます。<br>
         ![alt text](_assets/how_to_edit_01.png)
         <br>
         Ctrl + F で <strong>SLOPE_TITLE_CANDIDATES</strong> を検索します。<br>
         ![alt text](_assets/how_to_edit_08.png)
         <br>
         以下のように要素を追加します。<br>
         ```
         ("{帯タイトル}", "{帯タイトルの取得対象とする最初の1文字}", "{帯タイトルの取得対象とする最後の1文字}"),
         ```

6. "縦断曲線" 関係：
   1. ["縦断曲線長", "縦断曲線半径"] を取得するレイヤーは以下の通りです。
      - "D-STR-DIM"
      - "D-STR-HTXT"

      ※ 01_run.bat での実行に限りますが、取得対象を追加したい場合<br>
         メモ帳などで <strong>tools/controller.py</strong>を開きます。<br>
         ![alt text](_assets/how_to_edit_01.png)
         <br>
         Ctrl + F で <strong>DSTR_LAYERS</strong> を検索します。<br>
         ![alt text](_assets/how_to_edit_10.png)
         <br>
         以下のように要素を追加します。<br>
         ```
         # "D-STR-HTXT" を追加する場合
         DSTR_LAYERS: List[str] = [
            "D-STR-DIM",
            "D-STR-HTXT",
         ]
         ```

   2. "縦断曲線長" として識別するTEXTは以下の通りです。
      - "VCL=*"

      ※ 01_run.bat での実行に限りますが、取得対象を追加したい場合<br>
         メモ帳などで <strong>tools/controller.py</strong>を開きます。<br>
         ![alt text](_assets/how_to_edit_01.png)
         <br>
         Ctrl + F で <strong>VERTICAL_VCL_PREFIXES</strong> を検索します。<br>
         ![alt text](_assets/how_to_edit_11.png)
         <br>
         以下のように要素を追加します。<br>
         ```
         # "L=" を追加する場合
         VERTICAL_VCL_PREFIXES: List[str] = [
            "VCL=",
            "L=",
         ]
         ```

   3. "縦断曲線半径" として識別するTEXTは以下の通りです。
      - "VCR=*"
      - "R=*"

      ※ 01_run.bat での実行に限りますが、取得対象を追加したい場合<br>
         メモ帳などで <strong>tools/controller.py</strong> を開きます。<br>
         ![alt text](_assets/how_to_edit_01.png)
         <br>
         Ctrl + F で <strong>VERTICAL_VCR_PREFIXES</strong> を検索します。<br>
         ![alt text](_assets/how_to_edit_12.png)
         <br>
         以下のように要素を追加します。<br>
         ```
         # "RX=" を追加する場合
         VERTICAL_VCR_PREFIXES: List[str] = [
            "VCR=",
            "R=",
            "RX=",
         ]
         ```

   4. 縦断勾配 が２段の場合、["縦断曲線長", "縦断曲線半径"] が上手く取得できないことがあります。

---
---
# 4. フォルダ構成
- 以下の構成を崩さずに使用してください。
```

│
├─ README.*
│
├─ juudan_to_kikakouzou_ippan_extracter.exe
│
├─ juudan_to_kikakouzou_ippan_extracter.py
│
├─ _assets/
│
├─ _logs/
│
├─ venv/
│
├─ input/
│
├─ output/
│
├─ template/
│   └─ 幾何構造表（一般道）.xlsx
│
└─ tools/
　   ├─ controller.py      ← ★設定ファイル
　   ├─ belt_utils.py
　   ├─ find_belt_edges_by_text.py
　   ├─ count_paper_space_layouts.py
　   ├─ polyline_to_line_keep_others.py
　   ├─ sanitize_dxf_text.py
　   ├─ get_curvature.py
　   ├─ get_superelevation_runoff_rate.py
　   ├─ get_slope.py
　   └─ get_vertical_curve.py

```

---
---
# 5. フォルダ・ファイル説明

1. README.*
   - このファイルです。

2. juudan_to_kikakouzou_ippan_extracter.exe
   - このツールの実行ファイルです。

3. juudan_to_kikakouzou_ippan_extracter.py
   - このツールのメインスクリプトファイルです。

4. _assetsフォルダ
   - README.md用の置き場です。

5. _logsフォルダ
   - 実行ログファイルを保存する場所です。
   - 実行日から直近7日分を保存し、8日以前分は削除されます。

6. venvフォルダ
   - py実行時の仮想環境フォルダです。

7. inputフォルダ
   - 処理対象dxfファイルを保存する場所です。
   - 処理済のdxfファイルはinput\used_*フォルダに移動します。

8. outputフォルダ
   - 処理済のxlsxファイルはoutput\exec_*フォルダに保存されます。

9. templateフォルダ
   - 幾何構造表（一般道）.xlsx が置いてあります。

10. toolsフォルダ
   - juudan_to_kikakouzou_ippan_extracter.exe/py が参照する独自関数が置いてあります。


---
---
# 6. エラー対応

処理に問題が発生した場合は、以下の情報を管理者へ共有してください。

- _logs フォルダ内のログファイル（当該エラーが発生した時点のもの）
- 使用したDXFファイル
- 発生手順（どの操作でエラーが出たか簡単に）

例：
`01_run.bat 実行 → OKを押した直後にエラー`

※ログには実行時の設定値（controller.pyの内容）も記録されています。

---
---
# 7. 各種情報

## Requirement
* Python 3.14.6
* ezdxf 1.4.3

## Author
* 株式会社建設技術研究所
* 東北支社 道路・交通部
* 本間 京介

## License
* "juudan_to_kikakouzou_ippan_extracter" is Confidential.

---
---