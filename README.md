# Laya 爐石助手

以本機 Laya 多語模型做決策，透過 MuMu Android 模擬器操作爐石。從選擇牌組、排隊到對局結算，協助完成連續排位；操作使用 ADB 觸控，不占用 Windows 滑鼠。

[下載 release](https://github.com/ChienIKao/jev-hearthstone/releases) · [開發指南](docs/development.md) · [架構說明](docs/architecture.md) · [MIT License](LICENSE)

## 目前功能

- **連續排位**：依遊戲內牌組名稱選擇標準／開放模式，設定局數並自動接續對局。
- **對局操作**：起手換牌、出牌、攻擊、英雄能力、地標、發現／倒轉選牌及結束回合。
- **本機決策**：從遊戲提供的合法動作選擇，結合牌組打法、已知效果搜尋與 Laya 判斷。
- **牌組管理**：各自保存換牌、打法、combo 及環境筆記；可手動匯入 HSReplay 公開文字快照。
- **狀態檢視**：遊戲預覽、辨識結果、執行紀錄，以及 F8 停止。

每日、每週與活動任務尚未開放。這不是全卡牌模擬器，也不保證勝率；遇到未知效果時改由 Laya 從實際合法動作逐步選擇。

## 安裝

需要 **Windows、Python 3.12（含 Python Launcher）及 MuMu**。首次安裝需要網路，會下載 Python 相依套件、繁體中文卡牌資料及 Laya 多語模型。

1. 下載 release ZIP，或複製本儲存庫，放到可寫入的資料夾。
2. 雙擊 `setup.cmd`，等待出現 `Setup complete`。
3. 雙擊 `start.cmd` 開啟助手。

Release 是附安裝腳本的原始碼套件，不是免安裝執行檔。CPU 可執行；GPU 加速需另安裝相容的 PyTorch。升級時請保留自己的設定與資料，更新原始碼後重新執行 `setup.cmd`。

## 連接 MuMu

1. 在 MuMu 開啟爐石。在助手的「進階設定」填入 **ADB 路徑**與**裝置位址**，例如 `127.0.0.1:16384`；連接埠依實例而異。
2. 在 Android 爐石的下列檔案啟用 Power 日誌；若已有其他設定，保留原內容並加入或更新 `[Power]` 區段。

   ```text
   /sdcard/Android/data/com.blizzard.wtcg.hearthstone/files/log.config
   ```

   ```ini
   [Power]
   LogLevel=1
   FilePrinting=True
   Verbose=True
   ```

3. 重啟 **Android 爐石**，回到助手按「連線 MuMu」。
4. 在「遊戲畫面」按「更新預覽」，確認畫面與辨識資料。若觸控位置不符，可從進階設定校準。

連線和更新預覽只讀取狀態，不會自動出牌。MuMu 視窗不需維持前景，輸入座標依 Android 畫面比例與牌數配置計算。

## 開始排位

1. 在「牌組與環境」新增牌組，名稱必須與遊戲內相同，並選擇標準或開放。
2. 填寫換牌、打法與 combo 筆記，回到「排位作業」選定牌組。
3. 將遊戲停在主選單或牌組畫面，設定執行局數，再按「開始作業」。**0 表示持續執行**。
4. 按「停止作業」或 **F8** 取消後續輸入；關閉視窗也會要求停止。

正在進行中的對局可在「進階設定」使用「連續接手本局」。助手每次只執行一個動作，重新讀取局面後才繼續；未確認的操作會依條件重試一次或停止。牌組代碼僅保存，不會自動匯入遊戲。

## HSReplay 參考資料

在「牌組與環境」貼上 HSReplay 單一牌組的留牌指南或環境榜公開文字，填寫來源、分段與時間範圍，預覽後保存。這些資料是手動更新的快照，並非即時同步，也不會更動遊戲內牌組。

## 專案結構

```text
src/laya_hearthstone/   應用程式、決策、日誌讀取與裝置操作
tests/                 單元與回歸測試
scripts/               啟動、停止及資料下載工具
docs/                  架構、開發指南與版本說明
configs/               設定範例
assets/                畫面辨識圖樣
data/                  本機卡牌資料、對局紀錄與操作證據（不提交）
.cache/                本機模型快取（不提交）
setup.cmd              首次安裝／更新
start.cmd              開啟 MuMu 面板
pyproject.toml         Python 套件設定
```

既有 `deck-profiles.json`、`android-calibration.json` 等個人設定仍保存在專案根目錄，程式搬移不會重設它們。原始碼、模型、遊戲資料及個人設定的授權與存放方式不同；模型快取與對局紀錄不包含在 Git 儲存庫。

## 開發與驗證

```powershell
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
.venv\Scripts\python.exe scripts\bootstrap.py --offline
```

已完成龍戰整局實戰與換牌、發現、倒轉等操作驗證。測試紀錄只能證明當次流程與速度，不能推算勝率或所有卡牌的支援程度。更多 CLI、資料路徑及 Windows 實驗後端資訊見[開發指南](docs/development.md)。

## 授權與參考

本專案原始碼使用 [MIT License](LICENSE)。相依套件、模型、卡牌資料及遊戲素材保留各自的授權與權利；本專案與 Blizzard、MAA 或 HSReplay 無隸屬關係。

- [Laya](https://huggingface.co/convaiinnovations/laya)：本機有限選項決策。
- [MAA](https://github.com/MaaAssistantArknights/MaaAssistantArknights)、[MaaFramework](https://github.com/MaaXYZ/MaaFramework)：背景操作與桌面助手設計參考。
- [HearthstoneJSON](https://hearthstonejson.com/)：卡牌資料。
- [HSReplay](https://hsreplay.net/zh-hant/meta/)：牌組與留牌參考。
