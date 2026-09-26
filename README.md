# Laya 爐石助手

本機 Laya 多語模型 + Power.log 局面讀取 + 規則篩選 + Windows 滑鼠操作。

## 開始使用

1. 雙擊 `start.cmd`，會開啟控制面板並啟動讀取與 GPU 決策服務。每次開啟都是觀察模式。
2. 進入對局並手動完成起手換牌。
3. 按「校準座標」，把標記拖到對應英雄、英雄能力、結束回合、手牌及場上卡牌中心。Enter 儲存，Esc 取消。
4. 先按「只做一步」，在 3 秒內切回爐石並停住滑鼠。程式只執行一個當時仍有效的建議，然後根據日誌確認結果。
5. 確認座標正確後，可用「開始連續接手」。F8、Esc、切換視窗或手動移動滑鼠會停止。

新手牌張數需要校準一次；視窗改變尺寸需要重新校準。場上座標會依校準的間距推算，不同佈局仍需檢查。第一次出牌的真實 UI 成功率尚未驗證，請從單步開始。

`stop.cmd` 會停止本專案的控制面板、讀取器及決策服務（包含虛擬環境啟動器的子程序）。關閉面板會停止操作，背景讀取與決策仍會運行。

## 支援範圍

- 讀取双方英雄、手牌、手下、地點、武器、秘密數量、法力和遊戲提供的動作／目標清單。
- 每 100 毫秒讀取新增日誌；每兩秒檢查是否有新的遊戲工作階段。
- 一般手下／法術／武器出牌、攻擊、英雄能力、地點與結束回合的操作計畫。
- 每步驗證局面指紋、合法選項、前景視窗及尺寸；出手後等待日誌確認，失敗即停止，不盲目重試。
- 簡單、無觸發效果場面的攻擊斬殺搜尋，涵蓋嘲諷、聖盾、風怒與劇毒。未知效果、秘密與複雜觸發時不提供確定斬殺認證。
- 排除可見反傷造成的英雄自殺，以及未發現相關收益的滿血補血。
- 交換、可見死亡風險、費用組合、手牌／場位與資源保存的啟發式評分。這些評分不是完整對局模擬。
- Laya 比較規則選出的至多六個候選；選項模糊或明顯低分時使用規則排序。

起手換牌、發現、指定目標戰吼、泰坦、同一實體的特殊替代操作等目前交由人處理。斬殺搜尋尚未包含任意法術連段、所有新卡互動與未知秘密。純卡牌文字不能完整反映所有附魔和動態效果。

## 本機模型與資料

- Python 環境：`.venv`；Laya 0.3.20；PyTorch 2.11.0+cu128；RTX 4050。
- 模型放在 `.cache/huggingface`。運行時使用已下載快取，不將對局傳送給模型 API。
- `config.json` 記錄使用者確認的玩家名稱，每場重新對應 controller。
- `data/cards.zhTW.json` 為 HearthstoneJSON build 253216 的繁體中文卡牌資料。
- `state.json`：當前局面及讀取心跳。`observed_at` 是讀取器心跳，不代表每次都有新遊戲事件；`source_updated_at` 為日誌檔案更新時間。
- `advice.json`：建議、理由及方法。必須與目前局面指紋一致才能使用。
- `last-request.json`：最近的模型輸入。
- `execution.jsonl`：實際執行後的動作與確認結果。
- `sample-state.json`、`sample-advice.json`、`benchmark.json`、`replay-validation.json` 為歷史回放驗證，不能當成目前出牌指令。

模型分數未經爐石資料校準，不代表勝率。

## 測試

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p 'test_*.py'
```

目前的測試涵蓋局面更新、玩家映射、非法目標、斬殺順序、聖盾、秘密、補血、英雄反傷、費用組合、Windows 快照寫入重試、過期與尺寸檢查、動作日誌確認。UI 輸入仍須在實際視窗校準後做單步驗證。

來源：
- https://github.com/NandhaKishorM/laya
- https://hearthstonejson.com/docs/cards.html
- https://github.com/HearthSim/python-hslog

## 背景輸入實驗

面板預設勾選背景輸入，只允許單步；下拉選單可選 anchored_touch 或 postmessage。以下描述 PostMessage。它將視窗客戶區座標送至遊戲訊息佇列，不移動實體游標、不主動切換前景。訊息送出不代表遊戲接受；日誌未確認時停止，不回退到搶滑鼠模式。Windows 爐石相容性仍待實測。

參考 MaaFramework 的 Win32 控制方法分類與 Microsoft PostMessage 文件；本專案有自行實作的 PostMessage 後端，以及 MaaFramework 5.14.0 的 AnchoredTouch 觸控後端。AnchoredTouch 不移動游標，但目標受遮擋時可能短暫閃爍。兩種後端均不自動回退至實體滑鼠。
- https://github.com/MaaXYZ/MaaFramework/blob/main/docs/en_us/2.4-ControlMethods.md
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-postmessagew

## 從 repository 安裝

使用 Python 3.12 建立 `.venv`，安裝 `requirements.txt`；CUDA 版本的 PyTorch 請依本機 GPU 選擇官方套件。將 `config.example.json` 複製成 `config.json`，填寫自己的 BattleTag。`reader.py --logs` 可指定 Hearthstone Logs 路徑，預設為 `D:\Battle.net\Hearthstone\Logs`。

從 https://api.hearthstonejson.com/v1/253216/zhTW/cards.json 下載卡牌資料至 `data/cards.zhTW.json`。模型使用 `convaiinnovations/laya`；首次需先下載至專案 `.cache/huggingface`，目前 advisor 預設離線載入。模型、卡牌資料、校準、玩家設定及對局紀錄均不包含在 repository。


背景輸入診斷紀錄：實際測試過 PostMessage 拖牌，4 秒內日誌未確認；固定英雄位置背景右鍵未見選單，正常右鍵可見選單。這只能說本次 PostMessage 路徑未驗證成功，尚未確定內部原因。AnchoredTouch 已接入，真實對局成功與否需另行驗證。測試套件只驗證訊息、座標、停止時釋放觸點等程式行為，不能代替遊戲相容性測試。

## 2026-09-27 背景操作實測

目前預設後端為 `sendmessage_window`（MaaFramework SendMessageWithWindowPos）。本機對局中，英雄能力「變身」及拖出「後世之裔」各完成一次，均由遊戲日誌確認。此方法保持游標位置，短暫移動遊戲視窗以對齊游標，因此可能閃爍。只允許單步，尚不代表所有卡牌、指定目標或連續操作均已驗證。

`anchored_touch` 的拖牌及固定位置英雄能力測試都未獲日誌確認，保留為實驗選項。視窗對齊模式只允許位置平移，尺寸變更仍會停止。新手牌張數需核對推估位置；目前本機另已校準十張手牌，私人校準檔不會上傳。

助手視窗快捷鍵：F6 校準、F7 單步、F9 無目標且合法的英雄能力單步測試、F8 停止。英雄能力測試會實際消耗法力，只在你啟動後執行。
