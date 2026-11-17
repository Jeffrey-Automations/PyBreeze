# progress.md：PyBreeze 待辦

只放還沒做的事，一律以繁體中文記錄。做完就在同一個 commit 裡刪掉這條，並在 `docs/updates/` 新增一筆 `#done` 紀錄（格式與查詢方式見 `docs/updates/README.md`）。不放已完成的項目、不寫流水帳、不寫規則（規則在 `CLAUDE.md`）。
編號 `#n` 不重用。標記：〔決定〕需擁有者拍板、〔已決定〕擁有者已答覆、等著動手、〔阻塞〕在等別的事、〔未確認〕觀察到但還沒證實。
需要人在真正的機器、螢幕或瀏覽器上操作才能驗收的項目，一律放在最上面的「實體驗收」。
跨專案與工作區層級的待辦在 `D:\Codes\progress.md`（與本專案相關：X-1、X-17）。

## 實體驗收

- **#154** PySide6 6.12.0 與新版 je-editor 的組合只在 CI（offscreen）跑過測試，本機開發環境仍是 6.11.2（這台機器下載大型 wheel 會卡住）。
  要在實機上以 `pip install -r requirements.txt` 裝出 6.12.0，啟動 IDE 確認視窗、JupyterLab 分頁（QtWebEngine）與內嵌瀏覽器都正常；
  並量一次 `python -X importtime -c "import pybreeze.pybreeze_ui.editor_main.main_ui"`，把啟動時間補進 `architecture_explore.md`
  （JEditor 已不在啟動時匯入 AI 聊天面板與 IPython）。
- **#153** Nuitka 建出的執行檔還沒有在真正的機器上用過。CI 的 `nuitka-build` 會建置並檢查它（U-20261116-03）：知道自己是打包版、能當語言伺服器回應、IDE 在 offscreen 上能啟動；
  但沒有人在螢幕上操作過。從 `dev` 最近一次執行的 artifact **PyBreeze-windows** 下載，在一台沒有裝 Python 的 Windows 上確認：視窗與主題正常、
  開一個動作腳本（`.json`）有診斷與關鍵字補全、regex 測試器能跑、JupyterLab 分頁與內嵌瀏覽器（QtWebEngine）能開、關閉 IDE 後沒有留下 `PyBreeze.exe` 行程，
  沒有任何 Python 時 `.json` 檔仍會被告知是不是 JSON。`exe/automation_ide_setup_config.ifp`（InstallForge）仍指向舊名稱 AutomationIDE 與已不存在的檔案，屆時一併重做或刪除。
- **#152** 新版面還沒有在真正的螢幕上看過。導覽面板改成側邊欄的面板（U-20261115-01）之後，所有畫面都是以 offscreen 渲染擷取的。要在實機上確認：
  第一次啟動時側邊欄顯示導覽面板、活動列的指南針圖示可以切換、**檢視 ▸ 導覽** 有作用；切到檔案總管再關閉重開，會回到離開時的那個面板；
  JEditor Dark 與 JEditor Light 兩個主題下，PyBreeze 自己的工具分頁（cURL、HAR、JWT、Diff、SSH、AI、架構圖編輯器）文字與底色都看得清楚；
  高解析度縮放（125%、150%）下活動列圖示不模糊。
  另外 JupyterLab 分頁改成帶 token 載入（U-20261115-05）：伺服器端已用真正的 jupyter_server 驗過，但內嵌的畫面沒有在螢幕上開過，
  要確認分頁開得起來、不會停在登入頁，筆記本能執行。
- **#150** 工具分頁的截圖仍是 `dark_amber`：`images/tool_*.png`、兩張 montage、架構圖編輯器、SSH 用戶端、AI 與提示詞面板、prthinker 對話框、執行視窗。
  主視窗與三張選單已經以 JEditor Dark 重拍（U-20261115-02）。這些要帶著各自的範例資料重拍；`tool_response_inspector.png`、`tool_har_import.png`、
  `diagram_editor.png` 另外還停在換行與間距調整之前的樣子。
- **#134** 〔未確認〕教學 3 的瀏覽器範例（`docs/source/examples/first_browser_test.json`）從來沒有真的跑過：撰寫教學的環境沒有瀏覽器可以驅動。
  `test_tutorial_examples.py` 只核對關鍵字與參數，頁面上也只列出 `execute:` 那幾行並註明沒有執行過。要用 Chrome 實際跑一次，把真正的回傳值與報告內容補進中英文兩頁，再把那段註記拿掉。
- **#133** cURL Import 讀錯 Windows 上「Copy as cURL (cmd)」的格式，而且不會提示：`curl ^"http://127.0.0.1:8765/users.json^" ^` 加上
  `-H ^"Accept: application/json^"` 會得到網址 `^http://127.0.0.1:8765/users.json^` 與名稱為 `^Accept`、值以 `^` 結尾的標頭。`curl_parser` 會接起以 `^` 續行的行
  （`_LINE_CONTINUATION_RE`），但沒有還原 cmd 在引號與跳脫字元前加的 `^`。教學 6 目前請使用者改用 bash 格式。要修就得拿 Chrome、Edge、Firefox 實際複製出來的內容當測試樣本，
  發現問題的環境三個瀏覽器都跑不了。

## 待辦

### 相依套件與發佈

- **#121** 〔阻塞〕〔已決定：等正式推出且其他套件支援再說〕Python 3.15 上裝不了 PyBreeze：三個檔案都固定 `PySide6==6.11.2`，它的 wheel 標明 `Requires-Python <3.15`。
  PySide 的 `dev` 分支已把上限提到 `<3.16`，並把 QtWebEngine 拆成獨立的 `PySide6_WebEngine`；屆時要一併加上它（JEditor 的瀏覽器與 JupyterLab 分頁都用到），
  je-editor 與 frontengine 也要跟著動，再把 3.15 加進 CI、classifiers 與 README。
- **#125** 在 Linux 與 macOS 上跑完整的單元測試並設為發佈門檻；現在那兩個平台的工作只跑 smoke test。

### 等 JEditor 發佈

### PyBreeze 自己的功能

