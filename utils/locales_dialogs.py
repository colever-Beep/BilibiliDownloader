# utils/locales_dialogs.py
"""对话框 UI 翻译片段（CloseBehavior / Settings / Login / History / LiveRecord / BatchParse）。

FRAGMENT 格式：{ "简体中文": {"zh_TW": "...", "en": "...", "ja": "..."}, ... }
由 utils/i18n.py 自动发现并合并。
"""
# flake8: noqa

FRAGMENT = {
    # ---------- 关闭行为 ----------
    "关闭 B站下载器": {
        "zh_TW": "關閉 B站下載器",
        "en": "Close Bilibili Downloader",
        "ja": "Bilibiliダウンローダーを閉じる",
    },
    "要如何关闭程序？": {
        "zh_TW": "要如何關閉程式？",
        "en": "How do you want to close the program?",
        "ja": "プログラムをどう閉じますか？",
    },
    "检测到有下载任务正在进行，直接退出会中断下载。": {
        "zh_TW": "偵測到下載任務正在進行，直接結束會中斷下載。",
        "en": "A download is in progress; quitting now will interrupt it.",
        "ja": "ダウンロードが実行中です。そのまま終了すると中断されます。",
    },
    "可以让程序留在系统托盘后台继续运行，也可以完全退出。": {
        "zh_TW": "可讓程式留在系統托盤背景繼續執行，也可以完全結束。",
        "en": "You can keep it running in the system tray, or quit completely.",
        "ja": "システムトレイに常駐させて続行するか、完全に終了できます。",
    },
    "最小化到系统托盘（后台继续下载）": {
        "zh_TW": "最小化到系統托盤（背景繼續下載）",
        "en": "Minimize to system tray (keep downloading)",
        "ja": "システムトレイに最小化（バックグラウンドで継続）",
    },
    "直接关闭程序（结束所有任务）": {
        "zh_TW": "直接關閉程式（結束所有任務）",
        "en": "Quit directly (end all tasks)",
        "ja": "直接終了（すべてのタスクを終了）",
    },
    "记住我的选择，以后不再询问（可在设置中修改）": {
        "zh_TW": "記住我的選擇，以後不再詢問（可在設定中修改）",
        "en": "Remember my choice, don't ask again (changeable in settings)",
        "ja": "選択を記憶する（設定で変更可）",
    },

    # ---------- 设置：通用 ----------
    "设置": {
        "zh_TW": "設定",
        "en": "Settings",
        "ja": "設定",
    },
    "基本设置": {
        "zh_TW": "基本設定",
        "en": "General",
        "ja": "一般設定",
    },
    "视频设置": {
        "zh_TW": "影片設定",
        "en": "Video",
        "ja": "動画設定",
    },
    "附加内容": {
        "zh_TW": "附加內容",
        "en": "Extras",
        "ja": "追加コンテンツ",
    },
    "高级设置": {
        "zh_TW": "進階設定",
        "en": "Advanced",
        "ja": "詳細設定",
    },
    "下载路径:": {
        "zh_TW": "下載路徑:",
        "en": "Download path:",
        "ja": "ダウンロード先:",
    },
    "浏览": {
        "zh_TW": "瀏覽",
        "en": "Browse",
        "ja": "参照",
    },
    "FFmpeg 路径（留空则使用 bin/ffmpeg.exe）:": {
        "zh_TW": "FFmpeg 路徑（留空則使用 bin/ffmpeg.exe）:",
        "en": "FFmpeg path (leave empty to use bin/ffmpeg.exe):",
        "ja": "FFmpeg のパス（空欄で bin/ffmpeg.exe を使用）:",
    },
    "并行下载数:": {
        "zh_TW": "平行下載數:",
        "en": "Parallel downloads:",
        "ja": "並列ダウンロード数:",
    },
    "下载限速 (KB/s, 0=不限):": {
        "zh_TW": "下載限速 (KB/s, 0=不設限):",
        "en": "Download speed limit (KB/s, 0=unlimited):",
        "ja": "ダウンロード速度制限 (KB/s, 0=無制限):",
    },
    "同名文件处理:": {
        "zh_TW": "同名檔案處理:",
        "en": "Existing file handling:",
        "ja": "同名ファイルの処理:",
    },
    "为合集/多P视频创建单独文件夹": {
        "zh_TW": "為合集/多P影片建立單獨資料夾",
        "en": "Create a separate folder for collections / multi-part videos",
        "ja": "コレクション・複数話動画ごとにフォルダを作成",
    },
    "下载完成后自动打开下载目录": {
        "zh_TW": "下載完成後自動開啟下載目錄",
        "en": "Open the download folder automatically when finished",
        "ja": "ダウンロード完了後にフォルダを自動で開く",
    },
    "界面主题:": {
        "zh_TW": "介面主題:",
        "en": "Theme:",
        "ja": "テーマ:",
    },
    "界面语言:": {
        "zh_TW": "介面語言:",
        "en": "Language:",
        "ja": "言語:",
    },

    # ---------- 设置：主题设置 ----------
    "主题设置": {
        "zh_TW": "主題設定",
        "en": "Appearance",
        "ja": "テーマ設定",
    },
    "—— 主题色（强调色） ——": {
        "zh_TW": "—— 主題色（強調色） ——",
        "en": "—— Accent color ——",
        "ja": "—— アクセントカラー ——",
    },
    "自定义颜色": {
        "zh_TW": "自訂顏色",
        "en": "Custom color",
        "ja": "色を選択",
    },
    "—— 明暗主题 ——": {
        "zh_TW": "—— 明暗主題 ——",
        "en": "—— Light / Dark ——",
        "ja": "—— ライト / ダーク ——",
    },
    "明暗主题:": {
        "zh_TW": "明暗主題:",
        "en": "Theme mode:",
        "ja": "テーマモード:",
    },
    "选择主题色": {
        "zh_TW": "選擇主題色",
        "en": "Choose accent color",
        "ja": "アクセントカラーを選択",
    },
    "点击关闭按钮时:": {
        "zh_TW": "點擊關閉按鈕時:",
        "en": "When close button is clicked:",
        "ja": "閉じるボタンを押したとき:",
    },
    "每次询问": {
        "zh_TW": "每次詢問",
        "en": "Ask every time",
        "ja": "毎回確認",
    },
    "最小化到系统托盘": {
        "zh_TW": "最小化到系統托盤",
        "en": "Minimize to tray",
        "ja": "トレイに最小化",
    },
    "直接关闭程序": {
        "zh_TW": "直接關閉程式",
        "en": "Quit program",
        "ja": "プログラムを終了",
    },
    "自动重命名（推荐）": {
        "zh_TW": "自動重新命名（推薦）",
        "en": "Auto rename (recommended)",
        "ja": "自動リネーム（推奨）",
    },
    "覆盖已存在文件": {
        "zh_TW": "覆蓋已存在檔案",
        "en": "Overwrite existing file",
        "ja": "既存ファイルを上書き",
    },
    "查看日志": {
        "zh_TW": "查看日誌",
        "en": "View Log",
        "ja": "ログを見る",
    },
    "清晰度:": {
        "zh_TW": "畫質:",
        "en": "Quality:",
        "ja": "画質:",
    },
    "视频编码:": {
        "zh_TW": "影片編碼:",
        "en": "Video codec:",
        "ja": "動画エンコード:",
    },
    "封装格式:": {
        "zh_TW": "封裝格式:",
        "en": "Container format:",
        "ja": "コンテナ形式:",
    },
    "下载封面": {
        "zh_TW": "下載封面",
        "en": "Download cover",
        "ja": "カバー画像をダウンロード",
    },
    "将封面内嵌到视频文件（需开启下载封面）": {
        "zh_TW": "將封面內嵌到影片檔案（需開啟下載封面）",
        "en": "Embed cover into the video file (requires download cover)",
        "ja": "カバーを動画に埋め込む（カバーDL要）",
    },
    "内嵌后删除原封面文件（需开启『内嵌封面』）": {
        "zh_TW": "內嵌後刪除原封面檔案（需開啟『內嵌封面』）",
        "en": "Delete original cover after embedding (requires embed cover)",
        "ja": "埋め込み後に元のカバーを削除（埋め込み要）",
    },
    "—— 音频 ——": {
        "zh_TW": "—— 音訊 ——",
        "en": "—— Audio ——",
        "ja": "—— 音声 ——",
    },
    "音画分离（视频与音频分别保存为独立文件）": {
        "zh_TW": "音畫分離（影片與音訊分別儲存為獨立檔案）",
        "en": "Separate audio and video (saved as independent files)",
        "ja": "音声と映像を分離（別ファイルで保存）",
    },
    "仅下载音频（不下载视频流）": {
        "zh_TW": "僅下載音訊（不下載影片流）",
        "en": "Audio only (no video stream)",
        "ja": "音声のみ（映像ストリームなし）",
    },
    "音频格式:": {
        "zh_TW": "音訊格式:",
        "en": "Audio format:",
        "ja": "音声形式:",
    },
    "音频格式仅在「音画分离」或「仅下载音频」时生效，转码需要 FFmpeg": {
        "zh_TW": "音訊格式僅在「音畫分離」或「僅下載音訊」時生效，轉碼需要 FFmpeg",
        "en": "Audio format applies only when audio/video is separated or audio-only; transcoding needs FFmpeg",
        "ja": "音声形式は「分離」または「音声のみ」時のみ有効、変換には FFmpeg が必要",
    },
    "—— 弹幕 ——": {
        "zh_TW": "—— 彈幕 ——",
        "en": "—— Danmaku ——",
        "ja": "—— 弾幕 ——",
    },
    "下载弹幕": {
        "zh_TW": "下載彈幕",
        "en": "Download danmaku",
        "ja": "弾幕をダウンロード",
    },
    "弹幕格式:": {
        "zh_TW": "彈幕格式:",
        "en": "Danmaku format:",
        "ja": "弾幕形式:",
    },
    "xml 为 B 站原始格式，ass 可直接挂载播放器，json 便于二次处理": {
        "zh_TW": "xml 為 B 站原始格式，ass 可直接掛載播放器，json 便於二次處理",
        "en": "xml is Bilibili's native format, ass can be loaded by players directly, json is easy to reprocess",
        "ja": "xml は B 站の元形式、ass はプレーヤーに直接読込可、json は再処理に便利",
    },
    "—— 字幕（CC / AI 字幕） ——": {
        "zh_TW": "—— 字幕（CC / AI 字幕） ——",
        "en": "—— Subtitles (CC / AI) ——",
        "ja": "—— 字幕（CC / AI） ——",
    },
    "下载字幕": {
        "zh_TW": "下載字幕",
        "en": "Download subtitles",
        "ja": "字幕をダウンロード",
    },
    "字幕格式:": {
        "zh_TW": "字幕格式:",
        "en": "Subtitle format:",
        "ja": "字幕形式:",
    },
    "字幕语言:": {
        "zh_TW": "字幕語言:",
        "en": "Subtitle language:",
        "ja": "字幕言語:",
    },
    "需登录账号才能获取大部分稿件的字幕；无字幕的视频会自动跳过": {
        "zh_TW": "需登入帳號才能取得大部分稿件的字幕；無字幕的影片會自動跳過",
        "en": "Subtitles require login; videos without subtitles are skipped automatically",
        "ja": "字幕はログインが必要です。字幕のない動画は自動的にスキップされます",
    },
    "—— 元数据 ——": {
        "zh_TW": "—— 中繼資料 ——",
        "en": "—— Metadata ——",
        "ja": "—— メタデータ ——",
    },
    "保存元数据": {
        "zh_TW": "儲存中繼資料",
        "en": "Save metadata",
        "ja": "メタデータを保存",
    },
    "元数据格式:": {
        "zh_TW": "中繼資料格式:",
        "en": "Metadata format:",
        "ja": "メタデータ形式:",
    },
    "nfo 适用于 Kodi / Jellyfin / Emby 媒体库；内嵌需要 FFmpeg": {
        "zh_TW": "nfo 適用於 Kodi / Jellyfin / Emby 媒體庫；內嵌需要 FFmpeg",
        "en": "nfo works with Kodi / Jellyfin / Emby libraries; embedding needs FFmpeg",
        "ja": "nfo は Kodi / Jellyfin / Emby に対応、埋め込みには FFmpeg が必要",
    },
    "代理类型:": {
        "zh_TW": "代理類型:",
        "en": "Proxy type:",
        "ja": "プロキシ種類:",
    },
    "代理地址:": {
        "zh_TW": "代理位址:",
        "en": "Proxy host:",
        "ja": "プロキシアドレス:",
    },
    "代理端口:": {
        "zh_TW": "代理連接埠:",
        "en": "Proxy port:",
        "ja": "プロキシポート:",
    },
    "用户名 (可选):": {
        "zh_TW": "使用者名稱 (選填):",
        "en": "Username (optional):",
        "ja": "ユーザー名 (任意):",
    },
    "密码 (可选):": {
        "zh_TW": "密碼 (選填):",
        "en": "Password (optional):",
        "ja": "パスワード (任意):",
    },
    "仅对下载请求生效，登录仍使用系统网络": {
        "zh_TW": "僅對下載請求生效，登入仍使用系統網路",
        "en": "Applies to download requests only; login still uses the system network",
        "ja": "ダウンロード要求のみに適用、ログインはシステムのネットワークを使用",
    },
    "恢复默认": {
        "zh_TW": "恢復預設",
        "en": "Restore Defaults",
        "ja": "既定値に戻す",
    },
    "保存": {
        "zh_TW": "儲存",
        "en": "Save",
        "ja": "保存",
    },
    "取消": {
        "zh_TW": "取消",
        "en": "Cancel",
        "ja": "キャンセル",
    },
    "选择 FFmpeg 可执行文件": {
        "zh_TW": "選擇 FFmpeg 可執行檔",
        "en": "Select FFmpeg executable",
        "ja": "FFmpeg 実行ファイルを選択",
    },
    "可执行文件": {
        "zh_TW": "可執行檔",
        "en": "Executable",
        "ja": "実行ファイル",
    },
    "文本文件": {
        "zh_TW": "文字檔案",
        "en": "Text files",
        "ja": "テキストファイル",
    },
    "所有文件": {
        "zh_TW": "所有檔案",
        "en": "All files",
        "ja": "すべてのファイル",
    },
    "已恢复默认设置，点击“保存”生效。": {
        "zh_TW": "已恢復預設設定，點擊「儲存」生效。",
        "en": "Defaults restored. Click \"Save\" to apply.",
        "ja": "既定値を復元しました。「保存」で反映されます。",
    },
    "重置": {
        "zh_TW": "重置",
        "en": "Reset",
        "ja": "リセット",
    },

    # ---------- 登录 ----------
    "登录": {
        "zh_TW": "登入",
        "en": "Log In",
        "ja": "ログイン",
    },
    "粘贴 Cookie（支持 Netscape / 请求头 / JSON）": {
        "zh_TW": "粘貼 Cookie（支援 Netscape / 請求頭 / JSON）",
        "en": "Paste Cookie (supports Netscape / header / JSON)",
        "ja": "Cookie を貼り付け（Netscape / リクエストヘッダー / JSON 対応）",
    },
    "可从 Cookie-Editor 导出 Netscape，或粘贴浏览器请求头 Cookie / JSON": {
        "zh_TW": "可從 Cookie-Editor 匯出 Netscape，或粘貼瀏覽器請求頭 Cookie / JSON",
        "en": "Export Netscape from Cookie-Editor, or paste browser header Cookie / JSON",
        "ja": "Cookie-Editor で Netscape を出力するか、ブラウザのリクエストヘッダー Cookie / JSON を貼り付け",
    },
    "导入 cookies.txt": {
        "zh_TW": "匯入 cookies.txt",
        "en": "Import cookies.txt",
        "ja": "cookies.txt を読込",
    },
    "登录": {
        "zh_TW": "登入",
        "en": "Log In",
        "ja": "ログイン",
    },
    "取消": {
        "zh_TW": "取消",
        "en": "Cancel",
        "ja": "キャンセル",
    },
    "已导入：{}": {
        "zh_TW": "已匯入：{}",
        "en": "Imported: {}",
        "ja": "読込完了: {}",
    },
    "导入失败：{}": {
        "zh_TW": "匯入失敗：{}",
        "en": "Import failed: {}",
        "ja": "読込失敗: {}",
    },
    "错误": {
        "zh_TW": "錯誤",
        "en": "Error",
        "ja": "エラー",
    },
    "Cookie不能为空": {
        "zh_TW": "Cookie 不能為空",
        "en": "Cookie cannot be empty",
        "ja": "Cookie は空にできません",
    },
    "验证中...": {
        "zh_TW": "驗證中...",
        "en": "Verifying...",
        "ja": "検証中...",
    },
    "成功": {
        "zh_TW": "成功",
        "en": "Success",
        "ja": "成功",
    },
    "登录成功！\n用户：{}": {
        "zh_TW": "登入成功！\n使用者：{}",
        "en": "Logged in!\nUser: {}",
        "ja": "ログイン成功！\nユーザー: {}",
    },
    "登录成功：{}": {
        "zh_TW": "登入成功：{}",
        "en": "Logged in: {}",
        "ja": "ログイン成功: {}",
    },
    "失败": {
        "zh_TW": "失敗",
        "en": "Failed",
        "ja": "失敗",
    },
    "登录失败：Cookie无效或已过期\n请重新登录B站并导出Cookie": {
        "zh_TW": "登入失敗：Cookie 無效或已過期\n請重新登入 B站並匯出 Cookie",
        "en": "Login failed: Cookie is invalid or expired\nPlease log in to Bilibili again and export the Cookie",
        "ja": "ログイン失敗：Cookie が無効または期限切れです\nBilibiliに再ログインし Cookie を出力してください",
    },
    "登录失败：无法获取用户信息，请检查Cookie是否正确": {
        "zh_TW": "登入失敗：無法取得使用者資訊，請檢查 Cookie 是否正確",
        "en": "Login failed: cannot get user info, please check if the Cookie is correct",
        "ja": "ログイン失敗：ユーザー情報を取得できません。Cookie が正しいか確認してください",
    },
    "登录异常：{}": {
        "zh_TW": "登入異常：{}",
        "en": "Login error: {}",
        "ja": "ログイン例外: {}",
    },
    "异常：{}": {
        "zh_TW": "異常：{}",
        "en": "Error: {}",
        "ja": "例外: {}",
    },

    # ---------- 解析记录 / 历史 ----------
    "解析记录": {
        "zh_TW": "解析記錄",
        "en": "Parse History",
        "ja": "解析履歴",
    },
    "历史解析记录": {
        "zh_TW": "歷史解析記錄",
        "en": "History of Parsed Links",
        "ja": "解析履歴",
    },
    "搜索标题 / 链接 / 来源…": {
        "zh_TW": "搜尋標題 / 連結 / 來源…",
        "en": "Search title / link / source…",
        "ja": "タイトル / リンク / ソースを検索…",
    },
    "清空全部": {
        "zh_TW": "清空全部",
        "en": "Clear All",
        "ja": "すべて削除",
    },
    "刷新": {
        "zh_TW": "重新整理",
        "en": "Refresh",
        "ja": "更新",
    },
    "暂无解析记录": {
        "zh_TW": "暫無解析記錄",
        "en": "No parse records yet",
        "ja": "解析記録はありません",
    },
    "关闭": {
        "zh_TW": "關閉",
        "en": "Close",
        "ja": "閉じる",
    },
    "手动": {
        "zh_TW": "手動",
        "en": "Manual",
        "ja": "手動",
    },
    "收藏夹": {
        "zh_TW": "收藏夾",
        "en": "Favorites",
        "ja": "お気に入り",
    },
    "稍后再看": {
        "zh_TW": "稍後再看",
        "en": "Watch Later",
        "ja": "後で見る",
    },
    "历史记录": {
        "zh_TW": "歷史記錄",
        "en": "History",
        "ja": "履歴",
    },
    "添加": {
        "zh_TW": "新增",
        "en": "Add",
        "ja": "追加",
    },
    "提示": {
        "zh_TW": "提示",
        "en": "Notice",
        "ja": "ヒント",
    },
    "该视频已在队列中": {
        "zh_TW": "該影片已在佇列中",
        "en": "This video is already in the queue",
        "ja": "この動画はすでにキューにあります",
    },
    "解析失败": {
        "zh_TW": "解析失敗",
        "en": "Parse failed",
        "ja": "解析失敗",
    },
    "已添加: {}": {
        "zh_TW": "已新增: {}",
        "en": "Added: {}",
        "ja": "追加しました: {}",
    },
    "添加失败（可能已在队列）": {
        "zh_TW": "新增失敗（可能已在佇列）",
        "en": "Add failed (may already be in the queue)",
        "ja": "追加失敗（既にキューにある可能性があります）",
    },
    "添加异常: {}": {
        "zh_TW": "新增異常: {}",
        "en": "Add error: {}",
        "ja": "追加例外: {}",
    },
    "确认清空": {
        "zh_TW": "確認清空",
        "en": "Confirm Clear",
        "ja": "削除の確認",
    },
    "确定要清空所有历史记录吗？": {
        "zh_TW": "確定要清空所有歷史記錄嗎？",
        "en": "Are you sure you want to clear all history records?",
        "ja": "すべての履歴を削除しますか？",
    },
    "已清空": {
        "zh_TW": "已清空",
        "en": "Cleared",
        "ja": "クリア済み",
    },
    "历史记录已清空": {
        "zh_TW": "歷史記錄已清空",
        "en": "History cleared",
        "ja": "履歴を削除しました",
    },
    "清空失败: {}": {
        "zh_TW": "清空失敗: {}",
        "en": "Clear failed: {}",
        "ja": "削除失敗: {}",
    },

    # ---------- 录制直播 ----------
    "录制直播": {
        "zh_TW": "錄製直播",
        "en": "Record Live",
        "ja": "ライブ録画",
    },
    "直播间号或 URL：": {
        "zh_TW": "直播間號或 URL：",
        "en": "Live room ID or URL:",
        "ja": "配信ルーム番号または URL：",
    },
    "如: 123 或 https://live.bilibili.com/123": {
        "zh_TW": "如: 123 或 https://live.bilibili.com/123",
        "en": "e.g. 123 or https://live.bilibili.com/123",
        "ja": "例: 123 または https://live.bilibili.com/123",
    },
    "获取直播源": {
        "zh_TW": "取得直播源",
        "en": "Get Stream",
        "ja": "配信ソース取得",
    },
    "流地址：": {
        "zh_TW": "流位址：",
        "en": "Stream URL:",
        "ja": "ストリームURL：",
    },
    "输出文件名（可选）：": {
        "zh_TW": "輸出檔名（選填）：",
        "en": "Output filename (optional):",
        "ja": "出力ファイル名（任意）：",
    },
    "留空自动生成": {
        "zh_TW": "留空自動生成",
        "en": "Leave empty to auto-generate",
        "ja": "空欄で自動生成",
    },
    "自动重连（直播中断后继续录制）": {
        "zh_TW": "自動重連（直播中斷後繼續錄製）",
        "en": "Auto-reconnect (resume after interruption)",
        "ja": "自動再接続（中断後に継続）",
    },
    "就绪": {
        "zh_TW": "就緒",
        "en": "Ready",
        "ja": "準備完了",
    },
    "开始录制": {
        "zh_TW": "開始錄製",
        "en": "Start Recording",
        "ja": "録画開始",
    },
    "停止录制": {
        "zh_TW": "停止錄製",
        "en": "Stop Recording",
        "ja": "録画停止",
    },
    "请输入直播间号或 URL": {
        "zh_TW": "請輸入直播間號或 URL",
        "en": "Please enter the live room ID or URL",
        "ja": "ルーム番号または URL を入力してください",
    },
    "无法识别直播间号": {
        "zh_TW": "無法識別直播間號",
        "en": "Cannot recognize the live room ID",
        "ja": "ルーム番号を認識できません",
    },
    "正在获取直播信息...": {
        "zh_TW": "正在取得直播資訊...",
        "en": "Fetching live info...",
        "ja": "配信情報を取得中...",
    },
    "获取失败: {}": {
        "zh_TW": "取得失敗: {}",
        "en": "Fetch failed: {}",
        "ja": "取得失敗: {}",
    },
    "标题：{}\n主播：{}": {
        "zh_TW": "標題：{}\n主播：{}",
        "en": "Title: {}\nStreamer: {}",
        "ja": "タイトル：{}\n配信者：{}",
    },
    "当前未在直播": {
        "zh_TW": "目前未在直播",
        "en": "Not live right now",
        "ja": "現在配信中ではありません",
    },
    "获取流地址失败: {}": {
        "zh_TW": "取得流位址失敗: {}",
        "en": "Failed to get stream URL: {}",
        "ja": "ストリームURL取得失敗: {}",
    },
    "未找到流": {
        "zh_TW": "未找到流",
        "en": "No stream found",
        "ja": "ストリームが見つかりません",
    },
    "无法解析流地址": {
        "zh_TW": "無法解析流位址",
        "en": "Cannot resolve stream URL",
        "ja": "ストリームURLを解析できません",
    },
    "获取成功，可开始录制": {
        "zh_TW": "取得成功，可開始錄製",
        "en": "Ready, you can start recording",
        "ja": "取得成功、録画を開始できます",
    },
    "请先获取直播源": {
        "zh_TW": "請先取得直播源",
        "en": "Get the live stream first",
        "ja": "まず配信ソースを取得してください",
    },
    "录制中: {}": {
        "zh_TW": "錄製中: {}",
        "en": "Recording: {}",
        "ja": "録画中: {}",
    },
    "启动失败: {}": {
        "zh_TW": "啟動失敗: {}",
        "en": "Start failed: {}",
        "ja": "開始失敗: {}",
    },
    "已停止": {
        "zh_TW": "已停止",
        "en": "Stopped",
        "ja": "停止しました",
    },
    "停止失败: {}": {
        "zh_TW": "停止失敗: {}",
        "en": "Stop failed: {}",
        "ja": "停止失敗: {}",
    },
    "异常: {}": {
        "zh_TW": "異常: {}",
        "en": "Error: {}",
        "ja": "例外: {}",
    },

    # ---------- 直播中心 ----------
    "直播中心": {
        "zh_TW": "直播中心",
        "en": "Live Center",
        "ja": "ライブセンター",
    },
    "分区": {
        "zh_TW": "分區",
        "en": "Category",
        "ja": "カテゴリ",
    },
    "全站热门": {
        "zh_TW": "全站熱門",
        "en": "All Hot",
        "ja": "全体人気",
    },
    "搜索直播": {
        "zh_TW": "搜尋直播",
        "en": "Search Live",
        "ja": "ライブ検索",
    },
    "加载更多": {
        "zh_TW": "載入更多",
        "en": "Load More",
        "ja": "もっと読み込む",
    },
    "刷新": {
        "zh_TW": "重新整理",
        "en": "Refresh",
        "ja": "更新",
    },
    "人气": {
        "zh_TW": "人氣",
        "en": "Popularity",
        "ja": "人気",
    },
    "直播中": {
        "zh_TW": "直播中",
        "en": "Live",
        "ja": "配信中",
    },
    "未开播": {
        "zh_TW": "未開播",
        "en": "Offline",
        "ja": "配信外",
    },
    "正在加载直播列表...": {
        "zh_TW": "正在載入直播清單...",
        "en": "Loading live list...",
        "ja": "ライブ一覧を読み込み中...",
    },
    "加载直播列表失败：{}": {
        "zh_TW": "載入直播清單失敗：{}",
        "en": "Failed to load live list: {}",
        "ja": "ライブ一覧の読み込み失敗: {}",
    },
    "直播列表为空": {
        "zh_TW": "直播清單為空",
        "en": "Live list is empty",
        "ja": "ライブ一覧が空です",
    },
    "直播间加载失败：{}": {
        "zh_TW": "直播間載入失敗：{}",
        "en": "Failed to load room: {}",
        "ja": "ルームの読み込み失敗: {}",
    },

    # ---------- 批量解析 ----------
    "批量解析": {
        "zh_TW": "批次解析",
        "en": "Batch Parse",
        "ja": "一括解析",
    },
    "批量解析（一行一个链接，自动识别类型）": {
        "zh_TW": "批次解析（一行一個連結，自動識別類型）",
        "en": "Batch parse (one link per line, auto-detect type)",
        "ja": "一括解析（1行に1リンク、タイプを自動判別）",
    },
    "支持视频 / 合集 / UP主空间 / 番剧，自动区分并汇总到一个选择列表": {
        "zh_TW": "支援影片 / 合集 / UP主空間 / 番劇，自動區分並彙總到一個選擇清單",
        "en": "Supports videos / collections / uploader spaces / bangumi; auto-sorted into one selection list",
        "ja": "動画 / コレクション / 投稿者空間 / アニメに対応、自動判別して1つのリストに集約",
    },
    "开始解析": {
        "zh_TW": "開始解析",
        "en": "Start Parsing",
        "ja": "解析開始",
    },

    # ---------- 二维码登录 ----------
    "二维码登录": {
        "zh_TW": "二維碼登錄",
        "en": "QR Code Login",
        "ja": "QRコードログイン",
    },
    "Cookie": {
        "zh_TW": "Cookie",
        "en": "Cookie",
        "ja": "Cookie",
    },
    "请用哔哩哔哩App扫描二维码登录": {
        "zh_TW": "請用嗶哩嗶哩App掃描二維碼登錄",
        "en": "Scan the QR code with the Bilibili app",
        "ja": "BilibiliアプリでQRコードをスキャンしてください",
    },
    "刷新二维码": {
        "zh_TW": "重新整理二維碼",
        "en": "Refresh QR Code",
        "ja": "QRコードを更新",
    },
    "生成二维码中...": {
        "zh_TW": "產生二維碼中...",
        "en": "Generating QR code...",
        "ja": "QRコード生成中...",
    },
    "等待扫码...": {
        "zh_TW": "等待掃描...",
        "en": "Waiting for scan...",
        "ja": "スキャン待ち...",
    },
    "已扫码，请在手机上确认": {
        "zh_TW": "已掃碼，請在手機上確認",
        "en": "Scanned. Confirm on your phone.",
        "ja": "スキャン済み。スマホで確認してください",
    },
    "二维码已过期，请点击刷新": {
        "zh_TW": "二維碼已過期，請點擊重新整理",
        "en": "QR code expired. Click refresh.",
        "ja": "QRコードの有効期限切れ。更新してください",
    },
    "生成失败：{}": {
        "zh_TW": "產生失敗：{}",
        "en": "Generation failed: {}",
        "ja": "生成失敗：{}",
    },
    "网络错误：{}": {
        "zh_TW": "網路錯誤：{}",
        "en": "Network error: {}",
        "ja": "ネットワークエラー：{}",
    },
    "登录校验失败，请重试": {
        "zh_TW": "登錄校驗失敗，請重試",
        "en": "Login verification failed, please retry",
        "ja": "ログイン検証失敗、再試行してください",
    },
}
