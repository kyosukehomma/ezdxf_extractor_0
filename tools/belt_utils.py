from typing import Any, List, Tuple, Optional, Union
from tools import find_belt_edges_by_text   # 複数テキストを基準に帯の上端・下端を見つける

# ----------------------------
# Belt detection
# ----------------------------
def get_belt_y_positions(
    msp: Any,
    layer: str,
    merged_text: str,
    splited_start_text: str,
    splited_end_text: str,
) -> Tuple[Optional[float], Optional[float]]:
    """
    想定される帯タイトル文字列を基準に、帯の上端・下端の Y 座標を推定して返す。
        1) `merged_text`（例: 「曲率」）を上下のアンカーとして帯を探索。
        2) 見つからない場合は、分割タイトル（例: 「曲」と「率」など）で再探索。
        3) 見つかった帯の下端（min_y）と上端（max_y）を返す。

    Args:
        msp (Any)               : ezdxf の Modelspace。
        layer (str)             : タイトルテキストが存在するレイヤー名。
        merged_text (str)       : 結合済みの帯タイトル（上下に同じ語をアンカーとして指定）。
        splited_start_text (str): 分割タイトルの前半（下端側のアンカー文字列）。
        splited_end_text (str)  : 分割タイトルの後半（上端側のアンカー文字列）。

    Returns:
        Tuple[Optional[float], Optional[float]]:
            `(min_y, max_y)` を返す。探索に失敗した場合は `(None, None)`。

    Notes:
        - 内部で `tools.find_belt_edges_by_text.main()` を呼び出し、上下端の候補を抽出します。
        - `eps=1e-6`、`min_horizontal_length=1`、`pick_down="min"`, `pick_up="max"` の既存仕様を踏襲。
        - `line_layers=None`（線分補助なし）で探索します。
    """
    res = find_belt_edges_by_text.main(
        msp,
        text_layer=layer,
        anchor_down=merged_text,
        anchor_up=merged_text,
        pick_down="min",
        pick_up="max",
        eps=1e-6,
        line_layers=None,
        min_horizontal_length=1,
    )
    min_y = res.get("bottom_y")
    max_y = res.get("top_y")

    if min_y is None or max_y is None:
        # タイトルが分割されているものとする
        res = find_belt_edges_by_text.main(
            msp,
            text_layer=layer,
            anchor_down=splited_start_text,
            anchor_up=splited_end_text,
            pick_down="min",
            pick_up="max",
            eps=1e-6,
            line_layers=None,
            min_horizontal_length=1,
        )
        min_y = res.get("bottom_y")
        max_y = res.get("top_y")

    return min_y, max_y


# ----------------------------
# Text extraction
# ----------------------------
def get_texts_in_range(
    msp: Any,
    layer: Union[str, List[str]],
    min_y: float,
    max_y: float,
) -> List[Tuple[str, Tuple[float, float], float]]:
    """
    指定レイヤー（単一 or 複数）に属する TEXT のうち、Y 座標が指定範囲にあるものを抽出する。

    Args:
        msp   : ezdxf の Modelspace。
        layer : 抽出対象の TEXT レイヤー名（文字列 or 文字列リスト）。
        min_y : Y座標の下限（この値以上）。
        max_y : Y座標の上限（この値以下）。

    Returns:
        List[Tuple[str, Tuple[float, float], float]]:
            (text: str, position: (x: float, y: float), rotation_deg: float) のタプルのリスト。
    """
    # 帯が見つからないなどで None が渡るケースの保護
    if min_y is None or max_y is None:
        return []

    # 入力をリストに正規化
    layers: List[str] = [layer] if isinstance(layer, str) else list(layer or [])
    if not layers:
        return []

    results: List[Tuple[str, Tuple[float, float], float]] = []

    # レイヤーごとにクエリし、結果を合算
    for lyr in layers:
        # シングルクォートの安全なエスケープ（クエリ文字列破綻の予防）
        safe_lyr = str(lyr).replace("'", "\\'")
        for ent in msp.query(f"TEXT[layer=='{safe_lyr}']"):
            x, y = float(ent.dxf.insert[0]), float(ent.dxf.insert[1])
            if min_y <= y <= max_y:
                # TEXT は plain_text() が安全（タグなし）
                text = ent.plain_text()
                rotation = float(ent.dxf.rotation) % 360  # 0〜360 に正規化
                results.append((text, (x, y), rotation))

    return results