# progress.md：PyBreeze 待辦

只放還沒做的事，一律以繁體中文記錄。做完就在同一個 commit 裡刪掉這條，並在 `docs/updates/` 新增一筆 `#done` 紀錄（格式與查詢方式見 `docs/updates/README.md`）。不放已完成的項目、不寫流水帳、不寫規則（規則在 `CLAUDE.md`）。
編號 `#n` 不重用。標記：〔決定〕需擁有者拍板、〔已決定〕擁有者已答覆、等著動手、〔阻塞〕在等別的事、〔未確認〕觀察到但還沒證實。
需要人在真正的機器、螢幕或瀏覽器上操作才能驗收的項目，一律放在最上面的「實體驗收」。
跨專案與工作區層級的待辦在 `D:\Codes\progress.md`（與本專案相關：X-1、X-17）。

## 實體驗收

- **#152** 新版面還沒有在真正的螢幕上看過。導覽面板改成側邊欄的面板（U-20261115-01）之後，所有畫面都是以 offscreen 渲染擷取的。要在實機上確認：
  第一次啟動時側邊欄顯示導覽面板、活動列的指南針圖示可以切換、**檢視 ▸ 導覽** 有作用；切到檔案總管再關閉重開，會回到離開時的那個面板；
  JEditor Dark 與 JEditor Light 兩個主題下，PyBreeze 自己的工具分頁（cURL、HAR、JWT、Diff、SSH、AI、架構圖編輯器）文字與底色都看得清楚；
  高解析度縮放（125%、150%）下活動列圖示不模糊。
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

- **#27** 〔已決定：固定版本〕paramiko 沒有固定版本（`requirements.txt`、`pyproject.toml`、`dev.toml`），安裝時可能拿到仍有 CVE-2026-44405（SHA-1 RSA 簽章）的 4.x。
  程式不論版本都會在每次連線拒絕 SHA-1（`SHA1_ALGORITHMS`，U-20260923-40），SSH 測試在 5.0.0 上通過。要像 PySide6 那樣固定到確切版本。
- **#49** 〔已決定：固定版本〕jupyterlab 沒有固定版本。JupyterLab 分頁會在它執行的直譯器裡升級有問題的版本（`jupyter_lab_gui/jupyter_lab_thread.py`、
  `_VULNERABLE_RELEASES`），但安裝 PyBreeze 本身仍可能解析到那些版本；本 repo 的 `.venv` 是 jupyter_server 2.17.0、jupyterlab 4.5.6。
  上游已修：路徑穿越（CVE-2026-5422，2.18.2）、nbconvert 的儲存型 XSS（CVE-2026-44727，2.20.0）、5xx 時把 Referer 裡的 token 寫進 log（CVE-2026-86049，2.21.0）；
  jupyterlab 的 CVE-2026-42557（4.5.7）、CVE-2026-73415 與 CVE-2026-73417（4.5.10 / 4.6.2）。固定到 `jupyter_server` 2.21.0 以上、`jupyterlab` 4.5.10 以上的確切版本。
- **#53** 〔已決定：明確宣告並固定版本〕`requests`、`urllib3` 被直接匯入（`utils/network/public_http.py`、`http_client.py`、`url_validation.py`、三個 AI 面板）卻沒有宣告，
  版本隨自動化套件而定；`.venv` 的 urllib3 是 2.6.3，低於修掉 CVE-2026-44431 與 CVE-2026-44432 的 2.7.0。`public_http` 還依賴 urllib3 的 `_dns_host` 與 `http.client` 的
  `_create_connection`（`test_public_http.py` 守著，2.6.3 與 2.8.0 都通過）。`cryptography` 也是直接匯入（`connect_gui/ssh/ssh_key_loader.py`），只經由 paramiko 帶進來，
  `.venv` 是 46.0.6，低於修掉 CVE-2026-39892 的 46.0.7。`qt_material` 同樣只經由 je-editor 帶進來。四個都要宣告並固定。
- **#106** 〔已決定：要求 `test_pioneer>=0.1.34`〕`test_pioneer` 沒有固定版本，0.1.34 之前以系統語系的編碼讀 YAML：繁體中文 Windows（cp950）上，TestPioneer「Run YAML」
  遇到含非 ASCII 字元的檔案（編輯器存成 UTF-8）會以 `UnicodeDecodeError` 結束（`extend/process_executor/test_pioneer/test_pioneer_process_manager.py`）。`.venv` 是 0.1.30。
- **#109** 〔已決定：兩者都做〕`je-editor>=1.0.27` 允許環境留著 3.1.59 之前的 gitpython（CVE-2026-78676：寫設定時把引號內的值變成有效的 `core.hooksPath`；CVE-2026-78679）。
  je-editor 1.0.28 只多了 `gitpython>=3.1.59`，而 3.1.59 還有 CVE-2026-87818（diff API 的 `--no-index` 可讀任意路徑），3.1.60 修掉。要把下限改成 `je-editor>=1.0.28`
  並宣告 `gitpython>=3.1.60`。這一項與 #151 的「提高 je-editor 下限」一起做。
- **#112** 〔已決定：改用 Nuitka，兩份 auto-py-to-exe 設定可以刪除〕`exe/auto_py_to_exe_setting_linux.json` 與 InstallForge 專案 `exe/automation_ide_setup_config.ifp`
  仍以舊名稱 AutomationIDE 建置，指向已不存在的 `exe/start_automation_editor.py` 與 `exe/je_driver_icon.ico`。擁有者答覆寫的是「Nukita」，這裡當成 Nuitka；動手前先確認。
- **#121** 〔阻塞〕〔已決定：等正式推出且其他套件支援再說〕Python 3.15 上裝不了 PyBreeze：三個檔案都固定 `PySide6==6.11.2`，它的 wheel 標明 `Requires-Python <3.15`。
  PySide 的 `dev` 分支已把上限提到 `<3.16`，並把 QtWebEngine 拆成獨立的 `PySide6_WebEngine`；屆時要一併加上它（JEditor 的瀏覽器與 JupyterLab 分頁都用到），
  je-editor 與 frontengine 也要跟著動，再把 3.15 加進 CI、classifiers 與 README。
- **#125** 在 Linux 與 macOS 上跑完整的單元測試並設為發佈門檻；現在那兩個平台的工作只跑 smoke test。

### 等 JEditor 發佈

- **#151** 〔阻塞〕以下幾項已經在 JEditor 修掉（JEditor 的 U-20261115-01 ～ -05），等含這些修正的 je-editor 發佈之後，在這裡把下限提高、刪掉為舊版留的路徑，並更新文件：
  - 導覽面板的 dock 路徑（`NavigationDock`、`_add_navigation_dock()`、`~/.pybreeze/ui_state.json` 的 `navigation_visible`）與它的測試
    （`TestTheNavigationAsADock`、`test_navigation.py` 的 `in_a_dock`、`test_start_theme.py` 的 `dark_amber` 分支）。
  - `ui_overview.rst` 中英文兩頁開頭那段「搭配較早的 JEditor」的註記，以及 Sphinx「File / Run / Text」頁面裡「儲存、執行、除錯每次都會跳出另存新檔」的說明
    （JEditor 現在有檔案的分頁會存回原處，另有 **Save As**）。
  - 繁體中文介面裡 JEditor 自己的用語已改成執行、字型、終端機、停駐窗格，Dock 選單的子選單也翻了；確認與 PyBreeze 自己的用語一致（`test_traditional_chinese_uses_taiwan_terms`）。
  - 翻譯外掛的語言現在以它註冊的名稱列出（Sphinx Plugins 頁的法文範例會顯示 Français）。
  - 除錯器跑完之後同一個分頁可以再次除錯；設定檔的 `ui_style` 不是字串時不再讓 IDE 起不來；JEditor 自己的自動儲存不再問「檔案被外部修改」
    （`test_file_tree_rename.py` 兩個存檔測試為此擋掉分頁的監看訊號，可以拿掉）。
  - 啟動時不再匯入 AI 聊天面板與 IPython；在這裡重新量一次 `-X importtime`，更新文件裡的啟動時間。

### 仍要在 JEditor 動手

- **#117** 〔阻塞〕〔已決定：要讓 Variable Inspector 真的能用〕JEditor 的變數檢視器永遠是空的：`VariableModel` 顯示交給它的 `namespace`，但沒有任何程式給它
  （`je_editor/pyside_ui/code/variable_inspector/inspector_gui.py`）。要讓它能看到目前的變數值（IPython 主控台的 namespace，或暫停中的除錯器）。README 已不把它列為功能，Sphinx 頁面寫明是空的；修好後兩處都要改回來。
- **#120** 〔阻塞〕〔已決定：讓宿主提供子程序的環境變數〕用 JEditor 的 Run Program、Run Debugger 或 shell 跑 locust 腳本時，HttpUser 一次只跑一個：那些程序沿用 IDE 自己的環境
  （`subprocess.Popen` 沒給 `env`，`code_exec.py`、`shell_exec.py`），裡面帶著 PyBreeze 設的 `LOCUST_SKIP_MONKEY_PATCH`；10 個使用者的 3 秒測試跑了三分鐘以上。
  PyBreeze 自己的執行都經過 `child_environment()` 拿掉值為 `subprocess_util.IDE_ONLY` 的變數。JEditor 要讓宿主能提供它啟動程序時用的環境。
- **#129** 語言伺服器讀的是 IDE 啟動時那個直譯器的框架關鍵字（`PyBreezeMainWindow._offer_language_server()`）。之後從 Python 環境選單改選的直譯器，執行與 Automation Keywords 分頁會立刻採用，
  編輯器的補全與診斷卻要重啟才會跟上：JEditor 的 `DEFAULT_SERVERS` 每個副檔名只有一個指令，也沒有任何東西通知 PyBreeze 直譯器換了。要在選擇的地方加一個掛點
  （`build_venv_menu.py` 是 JEditor 的），再呼叫一次 `offer_to_jeditor()` 並重啟開著的 `.json` 分頁。

### PyBreeze 自己的功能

- **#89** 〔已決定：提供〕prthinker 設定有 Gemini、Cohere、Mistral 後端，卻沒有填金鑰的欄位：prthinker 從啟動 IDE 的環境讀取，對話框只在選到它們時顯示變數名稱
  （`KEY_FROM_ENVIRONMENT`，`dialog/prthinker_setting_dialog.py`）。要比照 OpenAI 與 Anthropic 加上密碼欄位，並與它們存在一起。
- **#92** 〔已決定：每次啟動產生一個 token，載入 view 時使用〕內嵌的 JupyterLab 沒有 token（`--ServerApp.token=`）：只綁 loopback 擋得住瀏覽器與別台機器，擋不住同一台機器上的其他帳號
  （RDS、實驗室的 Linux），它們能以 IDE 使用者的身分拿到 kernel。CLAUDE.md 的 Security › JupyterLab 規則要跟著改。
- **#111** 〔已決定：允許，在確認畫面明確顯示該位址後放行〕AI Code Review、CoT Code Review 與 Skill Send 拒絕本機與私有網路的端點（`validate_url`；`url_validation._is_blocked_ip`），
  所以本機的模型伺服器（Ollama、LM Studio、localhost 上的 prthinker）用不了。要讓使用者在看過位址的確認之後允許 loopback 或私有位址；CLAUDE.md 的 Security › Network 規則要跟著改。
- **#130** 〔決定〕JEditor 設定裡存的直譯器（`python_compiler`）每次啟動都被忘掉：`EditorMain.startup_setting()` 還原之後，`PyBreezeMainWindow.__init__` 又設成 `None`
  （`pybreeze/pybreeze_ui/editor_main/main_ui.py`）。拿掉那一行，執行、JupyterLab 分頁、prthinker 與語言伺服器就會從一開始用存下來的直譯器；但存下來的路徑可能已經不存在，要不要這樣做由擁有者決定。
- **#131** 〔決定〕MCP 用戶端只支援標準輸入輸出的傳輸。協定的 HTTP 傳輸多半用在同一台機器上的伺服器，而對外請求的規則（CLAUDE.md，Network）拒絕 loopback 與私有位址。
  要提供的話，得先決定使用者填在伺服器設定裡的網址能不能是 loopback（JupyterLab 分頁自己的伺服器就是），以及請求要帶什麼送出。
- **#132** MCP 用戶端分頁不會跟著伺服器的 `notifications/tools/list_changed`（resources 與 prompts 的也是）更新：通知到達的是讀取伺服器的那條執行緒，沒有東西把它帶到分頁。
  目前要重新連線才看得到新的工具。`McpClient.on_notification` 已經留好掛點；還缺一個送到 UI 執行緒的訊號，以及在不弄丟已輸入內容的前提下重填各頁。
  用戶端不提供伺服器 sampling、roots、elicitation 是既定決定（`docs/adr/0011`）。
- **#128** 打包版（`exe/`）沒有動作腳本的語言服務：`sys.executable` 是應用程式本身，沒有直譯器可以啟動 `extend/language_server/__main__.py`，`launch.can_serve()` 為 false。
  關鍵字探測在那裡仍然可用。缺的是啟動伺服器的方法：在打包的執行檔加第二個進入點（像 regex tester 的 worker），或用 PATH 上的直譯器並把 PyBreeze 的套件資料夾放進它的路徑。
