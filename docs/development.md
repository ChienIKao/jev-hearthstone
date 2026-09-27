# 開發指南

## 環境

在 Windows 使用 Python 3.12。從 checkout 進行 editable 安裝：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe scripts\bootstrap.py
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

`setup.cmd` 執行相同步驟。`scripts/bootstrap.py --offline` 會驗證既有卡牌資料與多語模型可載入；卡牌下載固定使用 HearthstoneJSON build 253216，模型為 `convaiinnovations/laya` 的 `multilingual` 子目錄。更新卡牌資料後，確切卡文核對可能使未重新驗證的效果退回未知邊界。

## 入口

| 用途 | 指令 |
| --- | --- |
| MuMu 面板 | `.venv\Scripts\python.exe -m laya_hearthstone.android_app` |
| MuMu 操作 CLI | `.venv\Scripts\python.exe -m laya_hearthstone.android_hands --help` |
| 日誌讀取 CLI | `.venv\Scripts\python.exe -m laya_hearthstone.android_reader --help` |
| 決策 CLI | `.venv\Scripts\python.exe -m laya_hearthstone.advisor --help` |
| 模型離線檢查 | `.venv\Scripts\python.exe scripts\bootstrap.py --offline` |

CLI 預設觀察或產生建議；執行操作需明確指定相應選項。歷史狀態可用 `advisor --state 檔案 --replay`，不會觸控遊戲。

`scripts/run.py` 是桌面啟動器，可在尚未 editable 安裝、但已有依賴的 checkout 中設定來源路徑後啟動指定角色。`start.cmd` 使用它開啟 MuMu 面板。`scripts/start.ps1` 提供背景啟動與 PID 記錄；其日誌在 `data/runtime/`。

## 本機資料

`src/laya_hearthstone/paths.py` 統一定位 checkout 根目錄，讀取位置不依賴目前工作目錄。

| 路徑 | 內容 |
| --- | --- |
| `deck-profiles.json` | 個人牌組、打法與匯入參考 |
| `android-calibration.json` | Android 相對觸控配置 |
| `data/cards.zhTW.json` | 卡牌資料 |
| `.cache/huggingface/` | 模型快取 |
| `data/android-evidence/` | 操作前後狀態、截圖與確認結果 |
| `data/ranked-decisions.jsonl` | 模型與規則決策、耗時與執行確認 |
| `data/ranked-results.jsonl` | 對局結果 |
| `data/device-locks/` | 防止多個控制器同時操作的裝置鎖 |

來源採 `src/` layout，執行測試前需 editable 安裝。`tests` 是獨立測試套件，測試共用 fixture 以套件路徑匯入。新程式模組放在 `src/laya_hearthstone/`，勿依賴根目錄的裸模組名稱。這份專案以 source checkout 執行，未提供獨立 wheel 的素材與本機資料部署流程。

## Windows 原生實驗後端

目前主要支援 MuMu。原生 Windows 輸入保留為實驗工具：

```powershell
& .\scripts\start.ps1 -Windows
& .\scripts\stop.ps1
```

Windows 腳本須符合本機 PowerShell 執行原則。從 `configs/config.example.json` 複製成根目錄的 `config.json` 後填寫 BattleTag；`reader --logs` 可指定 Windows 爐石日誌目錄。前景實驗輸入可能使用桌面滑鼠，與 MuMu ADB 觸控不同。

## 驗證範圍

回歸測試涵蓋日誌狀態、合法目標、輸入確認、換牌／選牌、搜尋邊界、斬殺與保命、token 預算及對手隱藏資訊隔離。既有標準龍戰單場驗證曾取得 37/37 操作確認、最慢決策 0.485 秒，結果落敗。測試與回放成功不代表已支援全部效果；有明顯誤判時，以對應的操作證據建立回歸案例。
