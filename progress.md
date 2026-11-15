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
- **#153** 打包還沒有實際建出執行檔驗過。打包工具已改成 Nuitka（`exe/build_nuitka.py`，U-20261116-02），這個腳本是照 Nuitka 的選項寫的，沒有跑過；
  打包版以 `PyBreeze --action-language-server` 啟動自己當語言伺服器（U-20261115-09），從原始碼以同一個進入點驗過（`test_language_server_launch.py`）。
  程式以 `sys.frozen` 判斷是不是打包版（語言伺服器、regex 測試器的 worker、預設直譯器、關鍵字探測），要確認 Nuitka 的 standalone 建置有設定它。
  `exe/automation_ide_setup_config.ifp`（InstallForge）仍指向舊名稱 AutomationIDE 與已不存在的檔案，建出執行檔後一併重做或刪除。要建一次，開一個動作腳本（`.json`）確認：
  有診斷與關鍵字補全、沒有多開一個 IDE 視窗、關閉 IDE 後沒有留下 `PyBreeze.exe` 行程；在沒有任何 Python 的機器上，`.json` 檔仍會被告知是不是 JSON。
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

- **#130** 〔決定〕JEditor 設定裡存的直譯器（`python_compiler`）每次啟動都被忘掉：`EditorMain.startup_setting()` 還原之後，`PyBreezeMainWindow.__init__` 又設成 `None`
  （`pybreeze/pybreeze_ui/editor_main/main_ui.py`）。拿掉那一行，執行、JupyterLab 分頁、prthinker 與語言伺服器就會從一開始用存下來的直譯器；但存下來的路徑可能已經不存在，要不要這樣做由擁有者決定。
- **#131** 〔決定〕MCP 用戶端只支援標準輸入輸出的傳輸。協定的 HTTP 傳輸多半用在同一台機器上的伺服器，而對外請求的規則（CLAUDE.md，Network）拒絕 loopback 與私有位址。
  要提供的話，得先決定使用者填在伺服器設定裡的網址能不能是 loopback（JupyterLab 分頁自己的伺服器就是），以及請求要帶什麼送出。
