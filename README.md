# Laya 爐石助手

本機 Laya 多語模型 + Power.log 局面讀取 + 規則篩選 + Windows 滑鼠操作。

## 開始使用

1. 雙擊 `start.cmd`，會開啟控制面板並啟動讀取與 GPU 決策服務。每次開啟都是觀察模式。
2. 進入對局並手動完成起手換牌。
3. 按「校準座標」，把標記拖到對應英雄、英雄能力、結束回合、手牌及場上卡牌中心。Enter 儲存，Esc 取消。
4. 按「開啟輸入測試台」，選擇後端、測試條件與目前合法動作，再按「開始測試」。背景模式不需切回遊戲；SendInput 前景對照才需在 3 秒內切回爐石。
5. 看日誌結果，再另外標記目視結果與備註。F8 可隨時停止；背景模式目前只允許單步。

座標依目前客戶區高度縮放、水平置中，支援移動及縮放視窗，並保留不同手牌張數的校準。操作途中改變尺寸會停止；過窄視窗使目標超出客戶區時不會點擊。場上座標會依校準的間距推算，不同佈局仍需檢查。目前僅有少量單步成功樣本，尚不能估計整體成功率。

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

## 手動輸入測試台

從主面板按「開啟輸入測試台」，或執行 `.venv\Scripts\python.exe app.py --test-ui`。開啟視窗不會操作遊戲。

可比較 Maa 普通 SendMessage、Maa PostMessage、簡易 PostMessage、AnchoredTouch、SendMessageWithWindowPos（視窗對齊）及 SendInput 前景對照。每次只執行你所選的合法動作；動作失效或換到另一場對局會取消，不改選其他卡牌。先在滑鼠靜止時測試，再比較移動滑鼠的條件。測試條件由你註記；程式記錄的是操作前後游標位置與前景狀態，不能證明中途完全沒有移動。

「已送出」僅表示輸入後端返回；「日誌已確認」表示觀察到預期局面變更。未確認不等於後端必然不支援。你可以選取紀錄查看座標，另填目視成功、無反應或點錯／不確定及備註。多人同時操作仍可能影響歸因。

`input-tests.jsonl` 保存執行結果，`test-observations.jsonl` 保存目視註記；兩者僅存在本機，不上傳 GitHub。測試台顯示最近 100 筆歷史以及本次新增紀錄。出牌及英雄能力測試會實際消耗資源，結束回合需手動選取再開始測試；指定目標戰吼尚未支援。「遊戲視窗復位」會最大化遊戲，執行中不可使用。

目前有日誌確認的樣本是視窗對齊模式的英雄能力、拖牌與英雄攻擊；PostMessage 與 AnchoredTouch 先前測試未獲確認，且過程曾有手動操作與座標干擾，不能由此判定兩者不可用。所有背景模式都不會自動回退至實體滑鼠。視窗對齊模式操作期間會完全透明、可穿透，還原位置後才恢復顯示；因此遊戲會暫時消失，並非全程可見的固定視窗。觸控模式在遮擋時可能閃爍。

跨螢幕時，先以未按下滑鼠的定位等待 DPI／客戶區尺寸穩定，再重算座標並執行；操作途中再次改變尺寸仍會停止。實測游標留在副螢幕、遊戲 DPI 從 96 變成 120 時，英雄攻擊已獲日誌確認。後續英雄能力測試也確認操作前後位置與客戶區尺寸一致。紀錄包含預定位 DPI、尺寸、最終位置及焦點，方便核對不同螢幕條件。

已知基礎費用為 0 的卡牌（例如幸運幣）即使日誌省略 COST，也會列入遊戲允許的動作；明確 COST 標籤優先。未知費用不會一律當作免費。練習模式已確認在 0 法力時成功打出幸運幣。

### 最小化實驗

選「視窗對齊 SendMessage」，勾選「最小化測試」，再選合法動作並開始。已最小化的遊戲也會自動走這個流程。Maa FramePool 將遊戲透明、可穿透地還原，輸入完成並確認日誌後再次最小化。這是透明還原的偽最小化，並非遊戲一直維持 Windows 最小化狀態。助手保持透明直到輸入後端完成清理、視窗位置及最小化狀態還原。

2026-09-27 練習模式實測：1920×1009 客戶區的最小化英雄能力，以及 1366×768 客戶區的最小化蜘蛛騎士拖牌，均獲日誌確認；兩次游標前後相同、遊戲前後不在前景，結束時恢復最小化。普通 SendMessage 的背景英雄能力樣本未獲確認。這些結果尚未涵蓋所有長寬比、DPI、多螢幕或完整連續對局。

測試紀錄另含擷取尺寸、客戶區座標及最小化前後狀態。關閉面板會先要求停止並等待輸入清理完成。

參考：
- https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/dev-v2/src/MaaCore/Controller/Win32Controller.cpp
- https://github.com/MaaXYZ/MaaFramework/blob/main/docs/en_us/2.4-ControlMethods.md
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-postmessagew

## 從 repository 安裝

使用 Python 3.12 建立 `.venv`，安裝 `requirements.txt`；CUDA 版本的 PyTorch 請依本機 GPU 選擇官方套件。將 `config.example.json` 複製成 `config.json`，填寫自己的 BattleTag。`reader.py --logs` 可指定 Hearthstone Logs 路徑，預設為 `D:\Battle.net\Hearthstone\Logs`。

從 https://api.hearthstonejson.com/v1/253216/zhTW/cards.json 下載卡牌資料至 `data/cards.zhTW.json`。模型使用 `convaiinnovations/laya`；首次需先下載至專案 `.cache/huggingface`，目前 advisor 預設離線載入。模型、卡牌資料、校準、玩家設定及對局紀錄均不包含在 repository。



