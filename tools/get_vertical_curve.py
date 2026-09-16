import re
from decimal import Decimal
from typing import Any, List, Tuple
from tools.get_slope  import get_slope_values
from tools.belt_utils import get_texts_in_range
from tools.controller import VERTICAL_VCR_PREFIXES, VERTICAL_VCL_PREFIXES

def get_vcr_vcl_values(
    texts_in_range: List[Tuple[str, Tuple[float, float], float]]
) -> Tuple[
        List[Tuple[Decimal, Tuple[float, float], float]],
        List[Tuple[Decimal, Tuple[float, float], float]]
    ]:
    """
    TEXT 文字列から VCR/R=... と VCL=... を抽出し、値を Decimal に数値化して返す。

    仕様:
        - VCR 系の接頭辞は複数対応（`"VCR="`, `"R="`）。
        - VCL 系は `"VCL="` に対応。
        - 接頭辞に一致した場合、1回だけ除去し、数値抽出では「数字と小数点のみ」を許容。
        - 小数点は最大 1 個まで許容。
        - 数値化（`Decimal(cleaned)`）に失敗した場合はその要素をスキップ。

    Args:
        texts_in_range (List[Tuple[str, Tuple[float, float], float]]):
            `(text, (x, y), rotation_deg)` のタプルのリスト（`get_texts_in_range` の出力）。

    Returns:
        Tuple[
            List[Tuple[Decimal, Tuple[float, float], float]],
            List[Tuple[Decimal, Tuple[float, float], float]]
        ]:
            `(vcr_values, vcl_values)` の2要素タプル。
            - それぞれのリスト要素は `(value: Decimal, position: (x, y), rotation_deg)`。

    Notes:
        - 数値抽出の正規化は正規表現 `[^0-9.]` で非数値文字を除去して実施。
        - `"R="` を VCR 系の別名として扱う既存仕様を踏襲。
    """

    vcr_values: List[Tuple[Decimal, Tuple[float, float], float]] = []
    vcl_values: List[Tuple[Decimal, Tuple[float, float], float]] = []

    # 除去対象ワードを事前にタプル化して startswith でまとめて判定できるようにしておく
    VCR_PREFIXES = tuple(VERTICAL_VCR_PREFIXES)
    VCL_PREFIXES = tuple(VERTICAL_VCL_PREFIXES)

    # 先に用意：数値抽出の正規化（数字と小数点のみ）
    NON_NUM_PATTERN = re.compile(r"[^0-9.]")

    for text, position, rotation in texts_in_range:
        if not isinstance(text, str):
            continue

        # --- VCR/R 系の判定 ---
        if text.startswith(VCR_PREFIXES):
            matched_prefix = next(p for p in VERTICAL_VCR_PREFIXES if text.startswith(p))
            value_str = text.replace(matched_prefix, "", 1).strip()
            cleaned = NON_NUM_PATTERN.sub("", value_str)
            if cleaned and cleaned.count(".") <= 1:
                try:
                    value = Decimal(cleaned)
                    vcr_values.append((value, position, rotation))
                except Exception:
                    # 変換失敗はスキップ
                    pass

        # --- VCL 系の判定 ---
        if text.startswith(VCL_PREFIXES):
            matched_prefix = next(p for p in VERTICAL_VCL_PREFIXES if text.startswith(p))
            value_str = text.replace(matched_prefix, "", 1).strip()
            cleaned = NON_NUM_PATTERN.sub("", value_str)
            if cleaned and cleaned.count(".") <= 1:
                try:
                    value = Decimal(cleaned)
                    vcl_values.append((value, position, rotation))
                except Exception:
                    # 変換失敗はスキップ
                    pass

    return vcr_values, vcl_values


def classify_vcr_by_slope(
    vcr_values:   List[Tuple[Decimal, Tuple[float, float], float]],
    slope_values: List[Tuple[Decimal, Tuple[float, float], float]]
) -> Tuple[List[Decimal], List[Decimal]]:
    """
    勾配の変化方向（増減）に基づき、VCR を 凸 (crest) / 凹 (sag) に分類して返す。

    判定ロジック（既存仕様踏襲）:
        - VCR の x より「右側」に位置する最初の勾配要素 i を見つける。
        - その i のひとつ左の勾配（prev）と i の勾配（next）を比較する。
            - prev > next → 凸 (crest)
            - prev < next → 凹 (sag)
        - prev/next の両方が存在しない場合（例: i == 0）は判定しない。

    前提:
        - `slope_values` は x 昇順でソート済み（`tools.get_slope.get_slope_values` の仕様）。

    Args:
        vcr_values (List[Tuple[Decimal, Tuple[float, float], float]]):
            VCR 値のリスト。各要素は `(vcr_value, (x, y), rotation_deg)`。
        slope_values (List[Tuple[Decimal, Tuple[float, float], float]]):
            勾配値のリスト。各要素は `(slope_value, (x, y), rotation_deg)`。

    Returns:
        Tuple[List[Decimal], List[Decimal]]:
            `(vcr_crest, vcr_sag)` の2要素タプル。
            - `vcr_crest`: 凸側に分類された VCR 値のリスト。
            - `vcr_sag`:   凹側に分類された VCR 値のリスト。

    Notes:
        - VCR ごとに最初に見つかった「右側の勾配」を用いて 1 回のみ判定します。
        - 判定不能の場合は該当 VCR をどちらにも追加しません。
    """

    vcr_crest: List[Decimal] = []
    vcr_sag:   List[Decimal] = []

    # 勾配は x 昇順で来ている前提（get_slope_values の仕様）
    # vcr_values は元の仕様通り、順次走査で判定
    for vcr_value, (vcr_x, _), _ in vcr_values:
        for i, (slope, (slope_x, _), _) in enumerate(slope_values):
            # VCR の X が 勾配の X より左にある場合
            if vcr_x < slope_x:
                # 前後の勾配値比較のため範囲チェック
                if 0 < i < len(slope_values):
                    prev_slope = slope_values[i - 1][0]  # 前の勾配値
                    next_slope = slope                  # 現在の勾配値

                    if prev_slope > next_slope:
                        vcr_crest.append(vcr_value)  # 凸
                        break
                    elif prev_slope < next_slope:
                        vcr_sag.append(vcr_value)    # 凹
                        break
                # i == 0 など、前が存在しない場合は判定不可 → 次へ
                break  # vcr_x < slope_x を満たしたので次の vcr へ

    return vcr_crest, vcr_sag


def init(
        msp: Any,
        dstr_layers: List[str]
    ) -> List[Tuple[str, Tuple[float, float], float]]:
    """
    DSTR レイヤー群から、全範囲（Y: -inf..+inf）の TEXT を抽出して返す初期化ヘルパー関数。

    Args:
        msp (Any): ezdxf の Modelspace。
        dstr_layers (List[str]): DSTR 系の TEXT レイヤー名一覧。

    Returns:
        List[Tuple[str, Tuple[float, float], float]]:
            `get_texts_in_range(msp, dstr_layers, -inf, +inf)` の結果。
            各要素は `(text: str, position: (x, y), rotation_deg: float)`。
    """
    texts_in_range = get_texts_in_range(msp, dstr_layers, float('-inf'), float('inf'))
    return texts_in_range


def main(msp: Any, dstr_layers: List[str], band_layer: str):
    """
    縦断曲線半径（凸/凹）と縦断曲線長の最小値を求めて返す。
        1) DSTR レイヤー群から TEXT を抽出（`init`）
        2) TEXT から VCR/R と VCL を抽出・数値化（`get_vcr_vcl_values`）
        3) BAND レイヤーから勾配を取得（TEXT の回転角度考慮あり：
            - `tools.get_slope.get_slope_values(msp, band_layer, True)`）
        4) 勾配の方向変化により VCR を 凸 / 凹 に分類（`classify_vcr_by_slope`）
        5) 各種最小値を算出し返却（凸半径最小 / 凹半径最小 / 曲線長最小）

    Args:
        msp (Any)               : ezdxf の Modelspace。
        dstr_layers (List[str]) : VCR/VCL を含む TEXT のレイヤー群（DSTR 系）。
        band_layer (str)        : 勾配（i）を取得する帯レイヤー名。

    Returns:
        Tuple[Any, Any, Any]:
            - `min_vcr_crest`: 凸側 VCR の最小値（Decimal）。値が無い場合は `"-"`。
            - `min_vcr_sag`  : 凹側 VCR の最小値（Decimal）。値が無い場合は `"-"`。
            - `min_vcl`      : VCL の最小値（Decimal）。値が無い場合は `"-"`。

    Notes:
        - 最小値の算出は、値が存在する場合は `min()`、存在しない場合は `"-"` を返す既存仕様。
        - 勾配値の取得は `tools.get_slope.get_slope_values` に依存し、x 昇順の前提で分類します。
        - VCR/R は両方を VCR 値として扱います（`"R="` を VCR の別名として許容）。
    """

    # DSTR の TEXT 取得
    texts_in_range = init(msp, dstr_layers)

    # VCR, VCL の抽出
    vcr_values, vcl_values = get_vcr_vcl_values(texts_in_range)

    # 勾配（TEXT の回転角度を考慮）を取得
    slope_values = get_slope_values(msp, band_layer, True)

    # 勾配に応じた VCR の分類
    vcr_crest, vcr_sag = classify_vcr_by_slope(vcr_values, slope_values)

    # 最小値の算出（仕様踏襲）
    min_vcr_crest = min(vcr_crest) if vcr_crest else "-"
    min_vcr_sag   = min(vcr_sag)   if vcr_sag   else "-"
    min_vcl       = min(val for val, _, _ in vcl_values) if vcl_values else "-"

    return min_vcr_crest, min_vcr_sag, min_vcl


# ----------------------------
# Entry Point
# ----------------------------
if __name__ == "__main__":
    pass