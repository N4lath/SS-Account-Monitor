# 8591 星塔旅人進度號 → Discord

監測所有伺服器的「星塔旅人／帳號／進度號」。GitHub Actions 每 10 分鐘檢查，發現新的商品編號就傳送到 Discord 文字頻道；電腦關機也能運作。

## 設定 Discord 通知

1. 先在 Discord 左側選一個伺服器，再選接收通知的文字頻道。建議使用自己建立的伺服器。
2. 點文字頻道旁的齒輪「編輯頻道」→「整合」→「Webhook」→「新增 Webhook」。複製 Webhook 網址。需要管理 Webhook 的權限。
3. 開啟本倉庫的 Settings → Secrets and variables → Actions → New repository secret。名稱填 DISCORD_WEBHOOK_URL，值填剛才複製的網址。網址不要放在程式、README 或聊天裡。
4. Actions →「8591 星塔旅人進度號監測」→ Run workflow，勾選「發送 Discord 連接測試」。確認頻道收到測試訊息。
5. 再執行一次，兩個測試選項都不勾選。日誌出現「已建立基準」即可；接著會定期檢查。
6. Discord 頻道的通知設定選擇「所有訊息」，確認手機 Discord 通知已開啟。
7. 如要 @自己，新增 DISCORD_USER_ID Secret，值為「使用者設定 → 進階 → 開發者模式」開啟後，對自己的頭像按右鍵複製的使用者 ID。

GitHub 設定入口：https://github.com/N4lath/SS-Account-Monitor/settings/secrets/actions

## 通知與去重

- 首次只記錄目前商品，避免把所有舊商品一次推送。
- 通知包含商品標題、NT$ 價格、伺服器、商品編號及商品連結。
- 按商品編號去重。改標題、降價或同編號重新上架不會重複通知；新編號視為新品。
- 待發與已發送記錄儲存在 .monitor/state.json。只有 Discord 確認成功才記為已發送；失敗則下次重試。
- 可設定 DISCORD_USER_ID Secret 為你的 Discord 使用者 ID，每則商品及測試訊息會 @該使用者。未設定則不標記任何人。
- 不會自動 @everyone。沒有新品時不發訊息。
- 請保留商品記錄；刪除後會重新建立基準。

## 執行與排程

需要 Python 3.11+ 與 curl，不需額外 Python 套件。

- python monitor.py --preview：讀取商品，不發通知、不更新記錄。
- python monitor.py --test-discord：發送連接測試。
- python monitor.py：讀取環境變數 DISCORD_WEBHOOK_URL 並執行一次檢查。

GitHub 手動執行提供「只測試 8591 讀取」和「發送 Discord 連接測試」兩個選項。正常監測時都不要勾選。

排程在每小時第 7、17、27、37、47、57 分鐘觸發。GitHub 可能延遲或丟棄排程，因此不保證上架後 10 分鐘內收到；兩次檢查之間就下架的商品可能錯過。

本機已驗證公開列表接口及篩選。雲端仍需實際確認讀取成功；8591 可能限制雲端來源或改動接口。讀取失敗、驗證頁面、分頁不完整都會讓工作流失敗並保留記錄。

30 天約 4,320 次執行。標準 GitHub 執行器用於公開倉庫通常免費；私有倉庫依方案有免費分鐘額度，超出可能計費或停止。公開倉庫連續 60 天無活動，排程可能停用。

## 維護

暫停：Actions → 此工作流 → 選單 → Disable workflow。恢復用 Enable workflow。

工作流需要提交 .monitor/state.json。若保存步驟失敗，檢查 Actions 讀寫權限、組織政策和分支保護。建議使用專用倉庫。

如果發送成功後程式中斷、或 GitHub 未能保存記錄，下一次可能重複一則通知。這是盡量避免漏通知的取捨。網站讀取失敗時可查看 Actions 的紅色失敗記錄，並開啟 GitHub 的失敗通知。

## 官方資料

- [8591 篩選頁面](https://www.8591.com.tw/v3/mall/list/66531?accountTag=3&searchType=2)
- [Discord Webhook 設定](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks)
- [GitHub 排程限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub Actions 計費](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
