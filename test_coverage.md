# 測試覆蓋度：PyBreeze

測量日期：2026-10-28。數字來自這台 Windows 機器上的一次實測，不是估計，也不是只數檔案。

| 項目 | 內容 |
|---|---|
| 直譯器 | 3.11.9 |
| 直譯器說明 | 專案 .venv。重掃。 |
| 工具 | coverage 7.15.0，`coverage run --branch` |
| 測量範圍 | `pybreeze` |
| 測試路徑 | `test/test_utils` |
| 命令 | `python -m coverage run --branch --source=pybreeze -m pytest test/test_utils` |
| 敘述覆蓋 | 99.14%（15419 / 15553） |
| 分支覆蓋 | 95.41%（3307 / 3466） |
| 測試結果 | 1 failed, 5021 passed, 18 skipped in 702.41s（pytest 結束碼 1） |
| 耗時 | 709.4 秒 |

敘述覆蓋是執行到的敘述數除以全部敘述數。分支覆蓋是執行到的分支數除以全部分支數。兩者分開算，沒有把分支混進敘述百分比。

## 這次怎麼量

測試跑的是 `test/test_utils`。這個目錄收集到 5040 則測試。`test/unit_test` 裡只有 `start_automation`，整包 `pytest test` 在收集時會直接結束，寫不出覆蓋度，所以沒有把那個目錄算進來。

## 覆蓋較低的檔案

只列這次測量裡敘述覆蓋最低的檔案，最多 12 個。

| 檔案 | 敘述覆蓋 | 已覆蓋 / 敘述 |
|---|---:|---:|
| `pybreeze\pybreeze_ui\mcp_gui\mcp_worker.py` | 83.33% | 20 / 24 |
| `pybreeze\utils\mcp\mcp_transport.py` | 93.55% | 87 / 93 |
| `pybreeze\extend\language_server\server_main.py` | 93.75% | 30 / 32 |
| `pybreeze\pybreeze_ui\mcp_gui\mcp_server_panel.py` | 94.78% | 109 / 115 |
| `pybreeze\utils\execution_report\report_files.py` | 95.12% | 78 / 82 |
| `pybreeze\utils\language_service\metadata_probe.py` | 95.35% | 41 / 43 |
| `pybreeze\pybreeze_ui\gui_thread_gc.py` | 95.65% | 22 / 23 |
| `pybreeze\utils\language_service\lsp_server.py` | 95.92% | 235 / 245 |
| `pybreeze\utils\execution_report\junit_xml.py` | 96.04% | 97 / 101 |
| `pybreeze\pybreeze_ui\connect_gui\ssh\ssh_file_viewer_widget.py` | 96.88% | 373 / 385 |
| `pybreeze\pybreeze_ui\editor_main\main_ui.py` | 97.42% | 151 / 155 |
| `pybreeze\pybreeze_ui\mcp_gui\mcp_profile_dialog.py` | 97.46% | 115 / 118 |

## 重掃（2026-10-28）

同一套覆蓋度命令再跑一次。覆蓋度與上次同一量級。下面是這次仍然失敗的測試。

- FAILED test/test_utils/test_metadata_probe.py::test_each_framework_lists_its_keywords_under_its_prefix[je_auto_control]
