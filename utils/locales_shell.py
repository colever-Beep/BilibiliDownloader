# utils/locales_shell.py
"""外壳 UI 翻译片段（main_window / sidebar / tray / log）。

FRAGMENT 格式：{ "简体中文": {"zh_TW": "...", "en": "...", "ja": "..."}, ... }
由 utils/i18n.py 自动发现并合并。
"""
# flake8: noqa

FRAGMENT = {
    # ---------- 主窗口 / 通用 ----------
    "BilibiliDownloader": {
        "zh_TW": "B站下載器 Pro",
        "en": "Bilibili Downloader Pro",
        "ja": "Bilibiliダウンローダー Pro",
    },
    "界面语言": {
        "zh_TW": "介面語言",
        "en": "Language",
        "ja": "言語",
    },
    "B站下载器": {
        "zh_TW": "B站下載器",
        "en": "Bilibili Downloader",
        "ja": "Bilibiliダウンローダー",
    },
    "粘贴B站链接（视频/合集/番剧/课程/音频/每周必看…）": {
        "zh_TW": "粘貼B站連結（影片/合集/番劇/課程/音訊/每週必看…）",
        "en": "Paste Bilibili link (video/collection/bangumi/course/audio/weekly…)",
        "ja": "Bilibiliのリンクを貼り付け（動画/コレクション/アニメ/講座/音声/週間…）",
    },
    "粘贴": {
        "zh_TW": "粘貼",
        "en": "Paste",
        "ja": "貼り付け",
    },
    "解析": {
        "zh_TW": "解析",
        "en": "Parse",
        "ja": "解析",
    },
    "批量解析（一行一个链接，自动识别类型）": {
        "zh_TW": "批次解析（一行一個連結，自動識別類型）",
        "en": "Batch parse (one link per line, auto-detect type)",
        "ja": "一括解析（1行に1リンク、タイプを自動判別）",
    },
    "搜索": {
        "zh_TW": "搜尋",
        "en": "Search",
        "ja": "検索",
    },
    "解析记录": {
        "zh_TW": "解析記錄",
        "en": "Parse History",
        "ja": "解析履歴",
    },
    "打开下载目录": {
        "zh_TW": "開啟下載目錄",
        "en": "Open Download Folder",
        "ja": "ダウンロードフォルダを開く",
    },
    "录制直播": {
        "zh_TW": "錄製直播",
        "en": "Record Live",
        "ja": "ライブ録画",
    },
    "总进度": {
        "zh_TW": "總進度",
        "en": "Overall Progress",
        "ja": "全体進捗",
    },
    "空闲": {
        "zh_TW": "閒置",
        "en": "Idle",
        "ja": "待機中",
    },
    "准备中…": {
        "zh_TW": "準備中…",
        "en": "Preparing…",
        "ja": "準備中…",
    },
    "全部结束": {
        "zh_TW": "全部結束",
        "en": "All Done",
        "ja": "すべて完了",
    },
    "开始下载": {
        "zh_TW": "開始下載",
        "en": "Start Download",
        "ja": "ダウンロード開始",
    },
    "取消": {
        "zh_TW": "取消",
        "en": "Cancel",
        "ja": "キャンセル",
    },
    "清空队列": {
        "zh_TW": "清空佇列",
        "en": "Clear Queue",
        "ja": "キューを空にする",
    },
    "下载中...": {
        "zh_TW": "下載中...",
        "en": "Downloading...",
        "ja": "ダウンロード中...",
    },
    "解析中...": {
        "zh_TW": "解析中...",
        "en": "Parsing...",
        "ja": "解析中...",
    },
    "取消中...": {
        "zh_TW": "取消中...",
        "en": "Cancelling...",
        "ja": "キャンセル中...",
    },
    "{}/{} 已完成": {
        "zh_TW": "{}/{} 已完成",
        "en": "{}/{} completed",
        "ja": "{}/{} 完了",
    },
    "下载完成": {
        "zh_TW": "下載完成",
        "en": "Download Complete",
        "ja": "ダウンロード完了",
    },
    "确认清空": {
        "zh_TW": "確認清空",
        "en": "Confirm Clear",
        "ja": "削除の確認",
    },
    "未登录": {
        "zh_TW": "未登入",
        "en": "Not Logged In",
        "ja": "未ログイン",
    },
    "请先登录以查看关注列表": {
        "zh_TW": "請先登入以查看關注列表",
        "en": "Please log in to view the following list",
        "ja": "フォロー一覧を見るにはログインしてください",
    },
    "请先登录以查看追番列表": {
        "zh_TW": "請先登入以查看追番列表",
        "en": "Please log in to view the anime list",
        "ja": "アニメリストを見るにはログインしてください",
    },
    "关注列表为空": {
        "zh_TW": "關注列表為空",
        "en": "Your following list is empty",
        "ja": "フォローリストが空です",
    },
    "追番列表为空": {
        "zh_TW": "追番列表為空",
        "en": "Your anime list is empty",
        "ja": "アニメリストが空です",
    },
    "每周必看为空或获取失败": {
        "zh_TW": "每週必看為空或取得失敗",
        "en": "Weekly Picks is empty or failed to fetch",
        "ja": "「今週の見どころ」が空か、取得に失敗しました",
    },
    "排行榜为空或获取失败": {
        "zh_TW": "排行榜為空或取得失敗",
        "en": "Ranking is empty or failed to fetch",
        "ja": "ランキングが空か、取得に失敗しました",
    },
    "该分类下无视频": {
        "zh_TW": "該分類下無影片",
        "en": "No videos in this category",
        "ja": "このカテゴリーには動画がありません",
    },
    "加载关注列表失败：{}": {
        "zh_TW": "載入關注列表失敗：{}",
        "en": "Failed to load following list: {}",
        "ja": "フォローリストの読み込みに失敗しました：{}",
    },
    "加载追番列表失败：{}": {
        "zh_TW": "載入追番列表失敗：{}",
        "en": "Failed to load anime list: {}",
        "ja": "アニメリストの読み込みに失敗しました：{}",
    },
    "加载每周必看失败：{}": {
        "zh_TW": "載入每週必看失敗：{}",
        "en": "Failed to load Weekly Picks: {}",
        "ja": "「今週の見どころ」の読み込みに失敗しました：{}",
    },
    "加载排行榜失败：{}": {
        "zh_TW": "載入排行榜失敗：{}",
        "en": "Failed to load ranking: {}",
        "ja": "ランキングの読み込みに失敗しました：{}",
    },
    "登录后才能查看历史记录": {
        "zh_TW": "登入後才能查看歷史記錄",
        "en": "Log in to view the watch history",
        "ja": "視聴履歴を見るにはログインが必要です",
    },
    "请先登录B站账号，否则无法获取稍后再看列表。": {
        "zh_TW": "請先登入B站帳號，否則無法取得稍後再看列表。",
        "en": "Please log in to your Bilibili account, otherwise the Watch Later list cannot be fetched.",
        "ja": "Bilibiliアカウントでログインしてください。そうでなければ「後で見る」リストを取得できません。",
    },
    "下载结束：完成{}，失败{}，取消{}\n保存路径: {}": {
        "zh_TW": "下載結束：完成{}，失敗{}，取消{}\n儲存路徑: {}",
        "en": "Download finished: {} completed, {} failed, {} cancelled\nSave path: {}",
        "ja": "ダウンロード終了：完了{}、失敗{}、キャンセル{}\n保存先: {}",
    },
    "确定要清空队列中的 {} 个任务吗？": {
        "zh_TW": "確定要清空佇列中的 {} 個任務嗎？",
        "en": "Are you sure you want to clear {} tasks from the queue?",
        "ja": "キューから {} 個のタスクを削除しますか？",
    },
    "开始下载 {} 个视频\n{}": {
        "zh_TW": "開始下載 {} 個影片\n{}",
        "en": "Starting download of {} videos\n{}",
        "ja": "{} 個の動画のダウンロードを開始\n{}",
    },

    # ---------- 侧边栏 ----------
    "语言": {
        "zh_TW": "語言",
        "en": "Language",
        "ja": "言語",
    },
    "登录": {
        "zh_TW": "登入",
        "en": "Log In",
        "ja": "ログイン",
    },
    "登出": {
        "zh_TW": "登出",
        "en": "Log Out",
        "ja": "ログアウト",
    },
    "请登录以使用更多功能": {
        "zh_TW": "請登入以使用更多功能",
        "en": "Please log in to use more features",
        "ja": "より多くの機能を使うにはログインしてください",
    },
    "我的收藏夹": {
        "zh_TW": "我的收藏夾",
        "en": "My Favorites",
        "ja": "マイ・お気に入り",
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
    "我的关注": {
        "zh_TW": "我的關注",
        "en": "My Following",
        "ja": "フォロー中",
    },
    "我的追番": {
        "zh_TW": "我的追番",
        "en": "My Bangumi",
        "ja": "フォロー中のアニメ",
    },
    "— 发现 —": {
        "zh_TW": "— 發現 —",
        "en": "— Discover —",
        "ja": "— 発見 —",
    },
    "每周必看": {
        "zh_TW": "每週必看",
        "en": "Weekly Must-watch",
        "ja": "週間おすすめ",
    },
    "排行榜": {
        "zh_TW": "排行榜",
        "en": "Ranking",
        "ja": "ランキング",
    },
    "搜索 B站": {
        "zh_TW": "搜尋 B站",
        "en": "Search Bilibili",
        "ja": "Bilibiliを検索",
    },
    "bilibili音乐": {
        "zh_TW": "bilibili音樂",
        "en": "Bilibili Music",
        "ja": "bilibiliミュージック",
    },
    "返回导航": {
        "zh_TW": "返回導航",
        "en": "Back to Nav",
        "ja": "ナビに戻る",
    },
    "加载收藏夹...": {
        "zh_TW": "載入收藏夾...",
        "en": "Loading favorites...",
        "ja": "お気に入りを読み込み中...",
    },
    "暂无收藏夹": {
        "zh_TW": "暫無收藏夾",
        "en": "No favorites yet",
        "ja": "お気に入りはまだありません",
    },
    "{}": {
        "zh_TW": "{}",
        "en": "{}",
        "ja": "{}",
    },
    "首次登录提醒 · B站接口调用限制": {
        "zh_TW": "首次登入提醒 · B站介面呼叫限制",
        "en": "First-login Notice · Bilibili API Limits",
        "ja": "初回ログインの注意 · Bilibili API の制限",
    },
    "登录后，本工具会以你的账号身份调用 B站 接口，请先了解以下限制：\n\n• 频率限制：B站接口有风控策略，短时间内大量请求可能被拦截（常见为 -352 / 412），表现为列表拉取失败或需要重新验证。\n\n• 批量操作：一次性解析收藏夹、历史记录、UP主空间等大列表时，建议分批进行并适当降低并行下载数。\n\n• 账号风险：频繁触发风控可能导致账号被临时限制部分功能，请勿用于高频自动化抓取。\n\n• 隐私说明：登录凭证（Cookie）仅保存在本机配置文件中，不会上传到任何服务器。\n\n点击「确定」继续登录，点击「取消」放弃登录。\n（本提醒仅首次显示）": {
        "zh_TW": "登入後，本工具會以你的帳號身分呼叫 B站 介面，請先了解以下限制：\n\n• 頻率限制：B站介面有風控策略，短時間內大量請求可能被攔截（常見為 -352 / 412），表現為清單拉取失敗或需要重新驗證。\n\n• 批次操作：一次性解析收藏夾、歷史記錄、UP主空間等大清單時，建議分批進行並適當降低平行下載數。\n\n• 帳號風險：頻繁觸發風控可能導致帳號被臨時限制部分功能，請勿用於高頻自動化抓取。\n\n• 隱私說明：登入憑證（Cookie）僅保存在本機設定檔中，不會上傳到任何伺服器。\n\n點擊「確定」繼續登入，點擊「取消」放棄登入。\n（本提醒僅首次顯示）",
        "en": "After logging in, this tool calls Bilibili's API using your account. Please understand the following limits first:\n\n• Rate limits: Bilibili applies risk-control to its API; a large number of requests in a short time may be blocked (commonly -352 / 412), causing list fetching to fail or requiring re-verification.\n\n• Batch operations: When parsing large lists such as favorites, watch history, or uploader spaces at once, it is recommended to do it in batches and lower the parallel download count.\n\n• Account risk: Frequently triggering risk-control may temporarily restrict some account features. Do not use this for high-frequency automated scraping.\n\n• Privacy: Login credentials (Cookie) are stored only in the local config file and are never uploaded to any server.\n\nClick \"OK\" to continue logging in, or \"Cancel\" to abort.\n(This reminder is shown only once)",
        "ja": "ログイン後、このツールはあなたのアカウントで Bilibili の API を呼び出します。続行前に以下の制限をご確認ください。\n\n• レート制限：Bilibili の API にはリスク管理があり、短時間に大量のリクエストを送るとブロックされる場合があります（一般的なエラーは -352 / 412）。リスト取得の失敗や再認証が求められることがあります。\n\n• 一括操作：お気に入りや視聴履歴、投稿者の空間などの大きなリストを一度に解析する場合は、バッチに分け、並列ダウンロード数を控えめにすることをおすすめします。\n\n• アカウントのリスク：リスク管理を頻繁に引き起こすと、一部の機能が一時的に制限される可能性があります。高頻度の自動収集には使用しないでください。\n\n• プライバシー：ログイン情報（Cookie）は本機の設定ファイルにのみ保存され、いかなるサーバーにも送信されません。\n\n「OK」をクリックするとログインを続行、「キャンセル」で中止します。\n（この注意は最初の1回のみ表示されます）",
    },

    # ---------- 系统托盘 ----------
    "隐藏窗口": {
        "zh_TW": "隱藏視窗",
        "en": "Hide Window",
        "ja": "ウィンドウを隠す",
    },
    "显示窗口": {
        "zh_TW": "顯示視窗",
        "en": "Show Window",
        "ja": "ウィンドウを表示",
    },
    "状态: 空闲": {
        "zh_TW": "狀態: 閒置",
        "en": "Status: Idle",
        "ja": "状態: 待機中",
    },
    "查看日志": {
        "zh_TW": "查看日誌",
        "en": "View Log",
        "ja": "ログを見る",
    },
    "退出": {
        "zh_TW": "退出",
        "en": "Exit",
        "ja": "終了",
    },

    # ---------- 日志窗口 ----------
    "日志": {
        "zh_TW": "日誌",
        "en": "Log",
        "ja": "ログ",
    },
    "共 {} 行": {
        "zh_TW": "共 {} 行",
        "en": "{} lines",
        "ja": "{} 行",
    },
    "清空日志": {
        "zh_TW": "清空日誌",
        "en": "Clear Log",
        "ja": "ログをクリア",
    },
    "即将清空日志窗口，同时会清空同目录下的 download.log 文件。\n是否继续？": {
        "zh_TW": "即將清空日誌視窗，同時會清空同目錄下的 download.log 檔案。\n是否繼續？",
        "en": "This will clear the log window and also empty the download.log file in the same folder.\nContinue?",
        "ja": "ログウィンドウをクリアすると、同じフォルダの download.log も空になります。\n続行しますか？",
    },
    "已清空": {
        "zh_TW": "已清空",
        "en": "Cleared",
        "ja": "クリア済み",
    },

    # ---------- 关于窗口 ----------
    "关于": {
        "zh_TW": "關於",
        "en": "About",
        "ja": "このアプリについて",
    },
    "关于": {
        "zh_TW": "關於",
        "en": "About",
        "ja": "このアプリについて",
    },
    "版本 1.0": {
        "zh_TW": "版本 1.0",
        "en": "Version 1.0",
        "ja": "バージョン 1.0",
    },
    "基于 CustomTkinter + yt-dlp 的\nB站视频 / 音频 / 弹幕 / 字幕下载工具": {
        "zh_TW": "基於 CustomTkinter + yt-dlp 的\nB站影片 / 音訊 / 彈幕 / 字幕下載工具",
        "en": "A Bilibili video / audio / danmaku / subtitle downloader\nbuilt on CustomTkinter + yt-dlp",
        "ja": "CustomTkinter + yt-dlp による\nBilibili 動画 / 音声 / 弾幕 / 字幕ダウンローダー",
    },
    "• 支持视频、番剧、课程、音频、歌单下载\n• 支持合集、UP主空间、每周必看、排行榜\n• 支持弹幕 / 字幕 / 封面 / 元数据下载\n• 支持直播录制、批量解析\n• 系统托盘后台运行、多语言切换": {
        "zh_TW": "• 支援影片、番劇、課程、音訊、歌單下載\n• 支援合集、UP主空間、每週必看、排行榜\n• 支援彈幕 / 字幕 / 封面 / 元資料下載\n• 支援直播錄製、批次解析\n• 系統托盤背景執行、多語言切換",
        "en": "• Download videos, bangumi, courses, audio, playlists\n• Support collections, uploader spaces, weekly picks, rankings\n• Support danmaku / subtitles / covers / metadata\n• Live recording, batch parsing\n• System tray background running, multi-language switching",
        "ja": "• 動画、アニメ、講座、音声、プレイリストのダウンロード\n• コレクション、投稿者スペース、週間おすすめ、ランキング対応\n• 弾幕 / 字幕 / 表紙 / メタデータのダウンロード\n• ライブ録画、一括解析\n• システムトレイ常駐、多言語切替",
    },
}
