import sys
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta
from pathlib import Path
import shutil
from typing import List, Tuple, Optional, Any
import logging

import ezdxf
from openpyxl import load_workbook

from tools import count_paper_space_layouts        # ペーパー空間のレイアウト数を取得する
from tools import polyline_to_line_keep_others     # LWPOLYLINをLINEに変換する
from tools import sanitize_dxf_text                # TEXTエンティティから空白文字等を除去する
from tools import get_curvature                    # 縦断図から値を取得する: 曲率
from tools import get_superelevation_runoff_rate   # 縦断図から値を取得する: 片勾配すり付け率
from tools import get_slope                        # 縦断図から値を取得する: 勾配
from tools import get_vertical_curve               # 縦断曲線半径, 縦断曲線長

from tools import controller
from tools.controller import (
    BAND_LAYERS,
    DSTR_LAYERS,
    SHEET_NAME,
    TEMPLATE_FILENAME_NO_EXT,
    EXT_XLSX,
    INPUT_DIR_NAME,
    OUTPUT_DIR_NAME,
    TEMPLATE_DIR_NAME,
    LOG_DIR_NAME,
    LOG_KEEP_DAYS,
    OUTPUT_PREFIX,
    USED_PREFIX,
)

# ----------------------------
# Path Utilities
# ----------------------------
def get_base_path() -> Path:
    """
    実行形態に応じてベースパス（実行ディレクトリ）を返す。
    - PyInstaller により exe として配布されている場合は、実行ファイルの親ディレクトリ。
    - Python スクリプトとして実行されている場合は、当該ファイル（__file__）の親ディレクトリ。

    Args: なし

    Returns:
        Path: ベースパスとなるディレクトリの `pathlib.Path`。

    Notes:
        - `sys.frozen` が存在する（PyInstaller でバンドルされた）場合の判断を行う。
    """

    if getattr(sys, "frozen", False):
        # PyInstaller で exe 化
        return Path(sys.executable).parent
    else:
        # Python スクリプトとして実行
        return Path(__file__).resolve().parent


# ----------------------------
# Logging
# ----------------------------
def log_controller_settings(logger: logging.Logger) -> None:
    logger.info("=== Controller Settings ===")

    for name in dir(controller):
        if name.isupper():
            try:
                value = getattr(controller, name)

                logger.info(f"{name}:")

                if isinstance(value, list):
                    for v in value:
                        logger.info(f"  - {v}")
                elif isinstance(value, tuple):
                    for v in value:
                        logger.info(f"  - {v}")
                else:
                    logger.info(f"  {value}")

            except Exception as e:
                logger.warning(f"{name}: 取得失敗 -> {e}")

    logger.info("================================")


def _prune_old_logs(logs_dir: Path, keep_days: int) -> None:
    """
    _logs ディレクトリ内のログファイルのうち、更新時刻が keep_days 日より古いものを削除する。

    Args:
        logs_dir (Path): ログディレクトリ（例: base_path / "_logs"）
        keep_days (int): 保持する日数（デフォルト 7）

    Returns: なし
    """
    try:
        cutoff = datetime.now() - timedelta(days=keep_days)
        for log_file in logs_dir.glob("run_*.log"):
            try:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff:
                    log_file.unlink(missing_ok=True)
            except Exception:
                # 個別ファイルで何か問題があっても他ファイルの削除は継続
                continue
    except Exception:
        # ディレクトリが無い or 権限等で失敗した場合も、アプリ起動は継続
        pass


def setup_logging(base_path: Path) -> logging.Logger:
    """
    ターミナル（標準出力）とファイル（`base_path/_logs/run_YYMMDD_HHMMSS.log`）へINFO レベル以上を出力するロガーを構成して返す。
    同一プロセス内での二重初期化を避けるため、ハンドラが既に存在する場合は既存ロガーをそのまま返す。

    Args:
        base_path (Path): ログディレクトリ `_logs` を作成する基準パス。

    Returns:
        logging.Logger: 構成済みのロガー。

    Notes:
        - 端末出力（StreamHandler）とファイル出力（FileHandler）を追加する。
        - ログフォーマットは `%(asctime)s [%(levelname)s] %(message)s`。
        - ファイルは UTF-8 で書き込む。
        - ルートロガーへの伝播は停止（`propagate=False`）。
    """

    logger = logging.getLogger("juudan_extracter")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # 上位ルートロガーへ伝播させない

    if logger.handlers:
        return logger  # 二重出力防止

    logs_dir = base_path / LOG_DIR_NAME
    logs_dir.mkdir(exist_ok=True)

    _prune_old_logs(logs_dir, keep_days=LOG_KEEP_DAYS)

    timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
    log_file_path = logs_dir / f"run_{timestamp}.log"

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(log_file_path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.info(f"ロギング初期化完了（ファイル: {log_file_path}）")
    return logger


# ----------------------------
# Excel Utilities
# ----------------------------
def open_or_create_sheet(wb, sheet_name: str):
    """
    指定名のワークシートが存在すればそれを返し、存在しなければ新規作成して返す。

    Args:
        wb              : `openpyxl.Workbook` インスタンス。
        sheet_name (str): 対象シート名。

    Returns:
        openpyxl.worksheet.worksheet.Worksheet: 対象ワークシート。
    """

    if sheet_name in wb.sheetnames:
        return wb[sheet_name]
    return wb.create_sheet(sheet_name)


def clear_target_cells(
        ws,
        rows: List[int],
        col_letter: str = "B"
    ) -> None:
    """
    指定列（デフォルト B列）の指定行セルをクリアする（セル値に `None` を代入）。

    Args:
        ws              : `openpyxl` の Worksheet。
        rows (List[int]): クリア対象の行番号リスト（例: `[1, 2, ..., 15]`）。
        col_letter (str): 列記号（例: `"B"`）。デフォルト `"B"`。

    Returns:
        None

    Examples:
        - `rows=[1,2,...,15], col_letter='B'` の場合、セル `B1..B15` をクリアします。
    """

    for r in rows:
        ws[f"{col_letter}{r}"] = None


def write_values(
        ws,
        values: List[Tuple[str, str, object]]
    ) -> None:
    """
    セルへ一括で値を書き込むユーティリティ。

    `values` は `(cell_addr, label, value)` のタプルのリストで、
    - `cell_addr` は「ラベル」を書き込む A列のアドレス（例: `"A12"`）
    - `label` は A列に書く見出し文字列
    - `value` は同じ行の B列に書く値（数値/文字列いずれでも可）

    Args:
        ws: `openpyxl` の Worksheet。
        values (List[Tuple[str, str, object]]): 書き込み指示のリスト。

    Returns:
        None

    Examples:
        - `("A1", "最小曲線半径", 500)` → `A1` に「最小曲線半径」、`B1` に `500` を書き込み。
    """

    for cell_addr, label, value in values:
        ws[cell_addr] = label
        row_num = "".join(filter(str.isdigit, cell_addr))  # "A12" -> "12"
        ws[f"B{row_num}"] = value


# ----------------------------
# Helpers for multi-band layers
# ----------------------------
def _is_number(x: Any) -> bool:
    """
    与えられた値が数値として扱えるかを判定する。

    - `float(x)` へ変換可能なら True。
    - `"inf"` / `"-inf"` も数値扱い。
    - 特に `"-"` は数値ではないものとして False を返す。

    Args:
        x (Any): 判定対象。

    Returns:
        bool: 数値として扱える場合 True、それ以外は False。
    """

    try:
        float(x)    # x を float変換できれば数値 ("inf"/"-inf" も数値扱い)
        return True
    except Exception:
        return False


def _first_valid_curvature(
        msp,
        band_layers: List[str],
        paper_layout_count: int,
        logger: logging.Logger
    ):
    """
    指定した band layer 群を先頭から順に試し、
    最初に有効な曲率帯情報が取得できた結果を返す。

    期待する戻り値（5要素タプル）:
        - `min_R_value`             : 最小曲線半径 R の値
        - `min_L_value_with_A`      : 緩和曲線長 L（緩和曲線 A あり）の最小値
        - `min_R_not_sandwiched_A`  : 緩和曲線（A）を省略できる曲線半径 R
        - `min_L_less`              : 設計速度 80km/h 未満での最小曲線長 L
        - `min_L_more`              : 設計速度 80km/h 以上での最小曲線長 L

    いずれの layer でも有効値が得られない場合は、5要素すべて `"-"` を返す。

    Args:
        msp                     : `ezdxf` の Modelspace。
        band_layers (List[str]) : 曲率帯検索対象のレイヤー名リスト。
        paper_layout_count (int): ペーパースペースのレイアウト数（抽出ロジックの補助情報）。
        logger (logging.Logger) : ログ出力用ロガー。

    Returns:
        Tuple[Any, Any, Any, Any, Any]:
            有効値が得られた場合は 5要素タプル、失敗時は `("-", "-", "-", "-", "-")`。

    Notes:
        - 内部で `tools.get_curvature.main(msp, layer, paper_layout_count)` を呼び出します。
        - 「有効値」の判定は、少なくとも `min_R_value` が数値であること。
    """

    for layer in band_layers:
        try:
            res = get_curvature.main(msp, layer, paper_layout_count)
            # 期待する戻り値: 5要素タプル
            (min_R_value, min_L_value_with_A, min_R_not_sandwiched_A, min_L_less, min_L_more) = res

            # 少なくとも R の最小値が数値なら採用（他は '-' の可能性も許容）
            if _is_number(min_R_value):
                logger.info(f"曲率帯の抽出成功（layer='{layer}'）")
                return res
        except Exception as e:
            logger.warning(f"曲率帯の抽出失敗（layer='{layer}'） -> {e}")
            continue
    # どれもだめならすべて '-'
    return ("-", "-", "-", "-", "-")


def _first_valid_runoff_rate(
        msp,
        band_layers: List[str],
        logger: logging.Logger
    ):
    """
    片勾配摺付率（runoff rate）を、指定した band layer を先頭から順に試し、
    **最初に取得できた有効な値**を返す。

    取得に失敗した場合は `"-"` を返す。

    Args:
        msp                     : `ezdxf` の Modelspace。
        band_layers (List[str]) : 対象レイヤー名リスト。
        logger (logging.Logger) : ログ出力用ロガー。

    Returns:
        Any: 片勾配摺付率（数値想定）。取得失敗時は `"-"`。

    Notes:
        - 内部で `tools.get_superelevation_runoff_rate.main(msp, layer)` を使用します。
    """

    for layer in band_layers:
        try:
            val = get_superelevation_runoff_rate.main(msp, layer)
            if val is not None:
                logger.info(f"摺付率の抽出成功（layer='{layer}'）")
                return val
        except Exception as e:
            logger.warning(f"摺付率の抽出失敗（layer='{layer}'） -> {e}")
    return "-"


def _max_slope(
        msp,
        band_layers: List[str],
        logger: logging.Logger
    ):
    """
    勾配（最急縦断勾配）を複数レイヤーから抽出し、**取得できた値の最大**を返す。

    いずれのレイヤーでも数値が得られない場合は `"-"` を返す。

    Args:
        msp                     : `ezdxf` の Modelspace。
        band_layers (List[str]) : 対象レイヤー名リスト。
        logger (logging.Logger) : ログ出力用ロガー。

    Returns:
        Any: 最大勾配（float を想定）。取得失敗時は `"-"`。

    Notes:
        - 内部で `tools.get_slope.get_max(msp, layer)` を使用します。
        - 数値判定には `_is_number` を用い、取得値を `float` に正規化して比較します。
    """

    values: List[float] = []
    for layer in band_layers:
        try:
            v = get_slope.get_max(msp, layer)
            if _is_number(v):
                values.append(float(v))
                logger.info(f"勾配抽出成功（layer='{layer}', value={v}）")
        except Exception as e:
            logger.warning(f"勾配抽出失敗（layer='{layer}'） -> {e}")
    return max(values) if values else "-"


def _min_vertical_curve(
        msp,
        dstr_layers: List[str],
        band_layers: List[str],
        logger: logging.Logger
    ):
    """
    縦断曲線情報（凸/凹 半径、および縦断曲線長）を複数レイヤーから抽出し、
    取得できた数値の最小を返す。

    抽出に失敗した種類は `"-"` を返す。

    Args:
        msp                     : `ezdxf` の Modelspace。
        dstr_layers (List[str]) : 寸法や文字などの構造関連レイヤー群（例: `"D-STR-DIM", "D-STR-HTXT"`）。
        band_layers (List[str]) : 帯レイヤー群（抽出対象）。
        logger (logging.Logger) : ログ出力用ロガー。

    Returns:
        Tuple[Any, Any, Any]:
            - `min_crest`: 最小の縦断曲線半径（凸）
            - `min_sag`  : 最小の縦断曲線半径（凹）
            - `min_vcl`  : 最小の縦断曲線長
            いずれか取得不能の種類は `"-"`。

    Notes:
        - 内部で `tools.get_vertical_curve.main(msp, dstr_layers, layer)` を呼び出します。
        - 数値判定には `_is_number` を使用し、比較時は `float` に正規化します。
    """

    crest_vals: List[float] = []
    sag_vals: List[float] = []
    vcl_vals: List[float] = []

    for layer in band_layers:
        try:
            crest, sag, vcl = get_vertical_curve.main(msp, dstr_layers, layer)
            if _is_number(crest):
                crest_vals.append(float(crest))
            if _is_number(sag):
                sag_vals.append(float(sag))
            if _is_number(vcl):
                vcl_vals.append(float(vcl))
            logger.info(f"縦断曲線抽出成功（layer='{layer}'）")
        except Exception as e:
            logger.warning(f"縦断曲線抽出失敗（layer='{layer}'） -> {e}")

    min_crest = min(crest_vals) if crest_vals else "-"
    min_sag   = min(sag_vals)   if sag_vals   else "-"
    min_vcl   = min(vcl_vals)   if vcl_vals   else "-"
    return min_crest, min_sag, min_vcl


# ----------------------------
# DXF Processing (single file)
# ----------------------------
def process_single_dxf(
        dxf_path: Path,
        logger: logging.Logger
    ) -> Optional[List[Tuple[str, str, object]]]:
    """
    1つの DXF を読み込み、必要な値を抽出して、
    Excel へ書き込む行の `(cell_addr, label, value)` のリストを返す。
    途中で例外が発生した場合は `None` を返す（呼び出し側でスキップする前提）。

    Args:
        dxf_path (Path)         : 入力 DXF ファイルのパス。
        logger (logging.Logger) : ログ出力用ロガー。

    Returns:
        Optional[List[Tuple[str, str, object]]]:
            成功時: Excel 書き込み指示のリスト（15項目）。
            失敗時: `None`。

    Notes:
        - 内部処理の主なステップ:
            1. ペーパースペースのレイアウト数を取得（`tools.count_paper_space_layouts`）
            2. DXF 読み込み（`ezdxf.readfile`）
            3. LWPOLYLINE を LINE に分解（`tools.polyline_to_line_keep_others`）
            4. MTEXT → TEXT 変換 & TEXT 文字クリーンアップ（`tools.sanitize_dxf_text`）
            5. モデルスペースを取得し、各種値を抽出（曲率/摺付率/勾配/縦断曲線）
        - 未定義項目は `"-"` 固定で返す。
    """

    try:
        logger.info(f"DXF 読込開始: {dxf_path.name} ({dxf_path.stat().st_size / 1024:.1f} KB)")

        # ペーパースペースのレイアウト数
        paper_layout_count = count_paper_space_layouts.main(str(dxf_path))

        # DXF 読込
        doc = ezdxf.readfile(str(dxf_path))

        # LWPOLYLINE を LINE に分解
        doc = polyline_to_line_keep_others.main(doc)

        # MTEXT → TEXT & TEXT 文字クリーンアップ
        doc = sanitize_dxf_text.main(doc)

        # モデルスペース
        msp = doc.modelspace()

        # 1) 曲率
        (
            min_R_value,
            min_L_value_with_A,
            min_R_not_sandwiched_A,
            min_L_value_with_R_less_80km_h,
            min_L_value_with_R_more_80km_h,
        ) = _first_valid_curvature(msp, BAND_LAYERS, paper_layout_count, logger)

        # 2) 片勾配打切半径（要件未定義）
        superelevation_cutoff_radius = "-"

        # 3) 片勾配摺付率
        max_fraction = _first_valid_runoff_rate(msp, BAND_LAYERS, logger)

        # 4) 勾配（最急縦断勾配：最大値）
        max_i_value = _max_slope(msp, BAND_LAYERS, logger)

        # 5) 特例値の縦断勾配を使用した際の制限長%, m（要件未定義）
        limit_length_percent = "-"
        limit_length_meter = "-"

        # 6) 縦断曲線半径（凸・凹）、縦断曲線長（最小値）
        min_vcr_crest, min_vcr_sag, min_vcl = _min_vertical_curve(msp, DSTR_LAYERS, BAND_LAYERS, logger)

        # 7) 視距（要件未定義）
        sight_distance = "-"

        # 8) 合成勾配（要件未定義）
        composite_gradient = "-"

        # Excel への書込行データ作成
        values: List[Tuple[str, str, object]] = [
            ("A1",  "最小曲線半径", min_R_value),
            ("A2",  "最小緩和曲線長", min_L_value_with_A),
            ("A3",  "緩和曲線を省略出来る曲線半径", min_R_not_sandwiched_A),
            ("A4",  "最小曲線長（設計速度80km/h未満）", min_L_value_with_R_less_80km_h),
            ("A5",  "最小曲線長（設計速度80km/h以上）", min_L_value_with_R_more_80km_h),
            ("A6",  "片勾配打切半径", superelevation_cutoff_radius),
            ("A7",  "片勾配摺付率", max_fraction),
            ("A8",  "最急縦断勾配", max_i_value),
            ("A9",  "特例値の縦断勾配を使用した際の制限長%", limit_length_percent),
            ("A10", "特例値の縦断勾配を使用した際の制限長m", limit_length_meter),
            ("A11", "縦断曲線半径凸", min_vcr_crest),
            ("A12", "縦断曲線半径凹", min_vcr_sag),
            ("A13", "縦断曲線長", min_vcl),
            ("A14", "視距", sight_distance),
            ("A15", "合成勾配", composite_gradient),
        ]

        logger.info(f"DXF 値抽出成功: {dxf_path.name}")
        return values

    except Exception as e:
        logger.error(f"DXF処理に失敗しました: {dxf_path.name} -> {e}")
        return None


# ----------------------------
# Main Processing (multiple files)
# ----------------------------

def proc() -> List[str]:
    """
    バッチ処理のエントリ：`input` フォルダ内のすべての `.dxf` を処理し、
    `template` フォルダのテンプレートに抽出値を書き込んだ Excel を
    `output/exec_YYMMDD_HHMMSS` に生成する。

    成功した DXF は `input/used_YYMMDD_HHMMSS` へ移動し、
    失敗した DXF は `input` に残る。

    Args: なし

    Returns:
        List[str]: 処理に成功した DXF ファイル名のリスト。

    Side Effects:
        - `base_path/_logs/run_YYMMDD_HHMMSS.log` にログファイルを作成。
        - `output/exec_YYMMDD_HHMMSS` と `input/used_YYMMDD_HHMMSS` を作成。
        - Excel ファイルを `output` 側へ出力・保存。
        - 成功ファイルを `input` → `input/used_...` へ移動。

    Notes:
        - 必須フォルダ `input` / `template` が無い場合はエラーダイアログ表示 & `sys.exit(1)`。
        - テンプレートファイル名は `幾何構造表（一般道）.xlsx` を想定。
        - Excel への書き込み時、シート名 `使用値` の B1〜B15 を一括クリア後、
          `process_single_dxf` からの値を反映する。
    """

    base_path = get_base_path()

    # ロギングを base_path/_logs で初期化
    logger = setup_logging(base_path)
    logger.info("処理開始")
    start_time = datetime.now()
    log_controller_settings(logger)

    input_folder_path    = base_path / INPUT_DIR_NAME
    output_folder_path   = base_path / OUTPUT_DIR_NAME
    template_folder_path = base_path / TEMPLATE_DIR_NAME

    # 必須フォルダ確認
    for folder in [input_folder_path, template_folder_path]:
        if not folder.exists():
            messagebox.showerror("Error", f"'{folder}' が存在しません。処理を中断します。")
            logger.error(f"必須フォルダなし: {folder}")
            sys.exit(1)

    # 出力フォルダ作成
    output_folder_path.mkdir(exist_ok=True)

    # タイムスタンプ & サブフォルダ
    timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
    input_subfolder_path  = input_folder_path / f"{USED_PREFIX}_{timestamp}"
    output_subfolder_path = output_folder_path / f"{OUTPUT_PREFIX}_{timestamp}"
    input_subfolder_path.mkdir(exist_ok=True)
    output_subfolder_path.mkdir(exist_ok=True)

    # テンプレートパス
    template_file_name = f"{TEMPLATE_FILENAME_NO_EXT}{EXT_XLSX}"
    template_file_path = template_folder_path / template_file_name
    if not template_file_path.exists():
        messagebox.showerror("Error", f"テンプレートが見つかりません: '{template_file_path}'")
        logger.error(f"テンプレートファイルなし: {template_file_path}")
        sys.exit(1)

    # .dxf を取得
    all_dxf_files = list(input_folder_path.glob("*.dxf"))
    logger.info(f"入力DXF件数: {len(all_dxf_files)}")
    if not all_dxf_files:
        logger.info("inputフォルダにDXFファイルがありませんでした。")
        return []

    processed_files: List[str] = []

    for dxf_path in all_dxf_files:
        logger.info(f"処理開始: {dxf_path.name}")

        # 値抽出
        values = process_single_dxf(dxf_path, logger)
        if values is None:
            logger.warning(f"値抽出に失敗したためスキップ: {dxf_path.name}")
            # Excel出力を行っていないため「移動しない」→ 失敗ファイルは input に残る
            continue

        # Excel 読込＆書込み
        try:
            wb = load_workbook(template_file_path)
            ws = open_or_create_sheet(wb, SHEET_NAME)

            # B列の対象行をクリア（B1〜B15）
            clear_target_cells(ws, rows=list(range(1, 16)), col_letter="B")

            # 書込み
            write_values(ws, values)

            # 保存ファイル名（テンプレート_元DXF名.xlsx）
            dxf_stem = dxf_path.stem
            xlsx_file_name = f"{TEMPLATE_FILENAME_NO_EXT}_{dxf_stem}{EXT_XLSX}"
            xlsx_file_path = output_subfolder_path / xlsx_file_name

            wb.save(xlsx_file_path)
            wb.close()
            logger.info(f"Excel出力成功: {xlsx_file_path}")

            # 出力成功時のみ移動
            shutil.move(str(dxf_path), str(input_subfolder_path))
            logger.info(f"移動完了: {dxf_path.name} -> {input_subfolder_path}")
            processed_files.append(dxf_path.name)

        except Exception as e:
            # 失敗時は移動しない（input に残る = 失敗ファイル）
            logger.error(f"Excel出力に失敗: {dxf_path.name} -> {e}")

    logger.info(f"出力成功件数: {len(processed_files)}")
    logger.info(f"出力失敗件数: {len(all_dxf_files) - len(processed_files)}")

    logger.info("処理終了")
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()

    logger.info(f"処理時間: {elapsed:.2f} 秒")

    return processed_files


# ----------------------------
# Entry Point
# ----------------------------
if __name__ == "__main__":
    print("juudan_to_kikakouzou_ippan_extracter [Version 1.0.1]")

    # Tkinter 初期化
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    # 実行確認
    start = messagebox.askokcancel("処理確認", "幾何構造表の作成を開始しますか？")

    if start:
        dxf_files = proc()

        # 完了メッセージ
        if dxf_files:
            title = "処理完了"
            message = "以下のDXFファイルを処理しました：\n" + "\n".join(dxf_files)
        else:
            title = "処理終了"
            message = "inputフォルダにDXFファイルがありませんでした。"
    else:
        title = "キャンセル"
        message = "処理をキャンセルしました。"

    messagebox.showinfo(title, message)