@echo off

echo ================================
echo ツールを起動します
echo ================================

if not exist venv\Scripts\activate (
    echo 仮想環境が見つかりません。
    echo 先に install.bat を実行してください。
    pause
    exit /b
)

call venv\Scripts\activate

python juudan_to_kikakouzou_ippan_extracter.py

echo.
echo ================================
echo 処理が終了しました
echo ================================
pause