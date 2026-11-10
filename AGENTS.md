# MPDL 專案維護

## 介面

後續 UI 一律沿用熊恩Sean「社群經營 x AI實戰」系列工具，細節見 `docs/UI樣式.md`。保持淺灰背景、白色圓角卡片、靛紫色主按鈕、圓形課程頭像與頁尾 Instagram／Facebook／Threads／LINE 四個連結。品牌圖片、CSS 和 JavaScript 由本機提供。使用台灣繁體中文，以清楚的操作步驟與錯誤提示為主。

## 開發與驗證

- 後端使用 Python 標準函式庫，下載透過官方 yt-dlp 與 FFmpeg。
- 變更網址、下載或 API 行為後，執行 `python3 -m unittest discover -s TubeDrop/tests -v`。
- UI 變更後檢查桌機與手機寬度、格式切換及平台辨識；更新 `docs/介面預覽.png`。
- 真實平台測試與限制記錄於 `docs/2026-11-10-下載驗證.md`，區分真實下載和模擬測試。

## 發布

GitHub 目標為 `SeanChen0427/MPDL`。公開內容包含程式、安裝入口、品牌素材與使用說明；下載媒體、封存、本機交接紀錄與執行時存取碼留在本機。遵循 `.gitignore`。專案支援 Mac 本機與 Docker 雲端模式；發布原始碼與部署可用網站是兩個不同動作。雲端部署須驗證實際服務網址、HTTPS 與真實影片，不可用本機測試宣稱雲端驗收。
