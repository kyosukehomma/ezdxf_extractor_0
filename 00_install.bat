@echo off


echo ================================
echo 環境セットアップを開始します
echo ================================


python --version
if %errorlevel% neq 0 (
    echo Pythonが見つかりません。
    echo Pythonをインストールしてから再実行してください。
    pause
    exit /b
)


echo.


if exist venv (
    echo 既存の仮想環境を使用します
) else (
    echo 仮想環境を作成します...
    python -m venv venv
)


echo.
echo 仮想環境を有効化します...
call venv\Scripts\activate


echo.
echo pip を更新します...
python -m pip install --upgrade pip


echo.
echo requirements.txt からライブラリをインストールします...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ライブラリのインストールに失敗しました
    pause
    exit /b
)


echo.
echo ================================
echo セットアップ完了
echo ================================
pause