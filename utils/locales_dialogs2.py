# utils/locales_dialogs2.py
"""对话框 UI 翻译片段（搜索 / 选择视频 / 下载选项 / 我的关注）。

FRAGMENT 格式：{ "简体中文": {"zh_TW": "...", "en": "...", "ja": "..."}, ... }
由 utils/i18n.py 自动发现并合并。
"""
# flake8: noqa

FRAGMENT = {
    # ---------- search_dialog ----------
    "封面": {
        "zh_TW": "封面",
        "en": "Cover",
        "ja": "サムネイル",
    },
    "标题 / UP主": {
        "zh_TW": "標題 / UP主",
        "en": "Title / Uploader",
        "ja": "タイトル / 投稿者",
    },
    "操作": {
        "zh_TW": "操作",
        "en": "Action",
        "ja": "アクション",
    },
    "时间": {
        "zh_TW": "時間",
        "en": "Time",
        "ja": "時間",
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
    "搜索视频 / 番剧 / UP主…": {
        "zh_TW": "搜尋影片 / 番劇 / UP主…",
        "en": "Search video / bangumi / uploader…",
        "ja": "動画 / アニメ / 投稿者を検索…",
    },
    "搜索音乐 / MV / 歌单…": {
        "zh_TW": "搜尋音樂 / MV / 歌單…",
        "en": "Search music / MV / playlist…",
        "ja": "音楽 / MV / プレイリストを検索…",
    },
    "搜索": {
        "zh_TW": "搜尋",
        "en": "Search",
        "ja": "検索",
    },
    "搜索当前列表（标题 / UP主）…": {
        "zh_TW": "搜尋目前清單（標題 / UP主）…",
        "en": "Filter current list (title / uploader)…",
        "ja": "現在のリストを検索（タイトル / UP主）…",
    },
    "添加到下载队列": {
        "zh_TW": "新增至下載佇列",
        "en": "Add to download queue",
        "ja": "ダウンロードキューに追加",
    },
    "浏览TA的个人空间": {
        "zh_TW": "瀏覽TA的個人空間",
        "en": "View their profile",
        "ja": "TAの個人ページを見る",
    },
    "浏览该视频的分集": {
        "zh_TW": "瀏覽該影片的分集",
        "en": "View video episodes",
        "ja": "動画のエピソードを見る",
    },
    "下一步": {
        "zh_TW": "下一步",
        "en": "Next step",
        "ja": "次へ",
    },
    "排序": {
        "zh_TW": "排序",
        "en": "Sort",
        "ja": "並び替え",
    },
    "默认排序": {
        "zh_TW": "預設排序",
        "en": "Default",
        "ja": "既定の並び",
    },
    "按发布时间": {
        "zh_TW": "依發布時間",
        "en": "By publish time",
        "ja": "投稿日時順",
    },
    "按播放量": {
        "zh_TW": "依播放量",
        "en": "By views",
        "ja": "再生数順",
    },
    "按时长": {
        "zh_TW": "依時長",
        "en": "By duration",
        "ja": "長さ順",
    },
    "按标题": {
        "zh_TW": "依標題",
        "en": "By title",
        "ja": "タイトル順",
    },
    "收藏夹为空，没有可下载的视频": {
        "zh_TW": "收藏夾中沒有可下載的影片",
        "en": "No downloadable videos in this favorites folder",
        "ja": "このお気に入りフォルダーにダウンロード可能な動画はありません",
    },
    "历史记录为空，没有可下载的视频": {
        "zh_TW": "歷史記錄中沒有可下載的影片",
        "en": "No downloadable videos in watch history",
        "ja": "視聴履歴にダウンロード可能な動画はありません",
    },
    "稍后再看列表为空，没有可下载的视频": {
        "zh_TW": "稍後再看清單中沒有可下載的影片",
        "en": "No downloadable videos in Watch Later",
        "ja": "「後で見る」にダウンロード可能な動画はありません",
    },
    "该UP主暂无可下载视频": {
        "zh_TW": "該UP主目前沒有可下載的影片",
        "en": "This uploader has no downloadable videos",
        "ja": "この投稿者にダウンロード可能な動画はありません",
    },
    "输入关键词后点击搜索": {
        "zh_TW": "輸入關鍵字後點擊搜尋",
        "en": "Enter a keyword then click Search",
        "ja": "キーワードを入力して検索をクリック",
    },
    "暂无搜索结果": {
        "zh_TW": "暫無搜尋結果",
        "en": "No search results",
        "ja": "検索結果はありません",
    },
    "未找到音乐相关视频": {
        "zh_TW": "未找到音樂相關影片",
        "en": "No music videos found",
        "ja": "音楽動画が見つかりません",
    },
    "添加全部视频结果": {
        "zh_TW": "新增全部影片結果",
        "en": "Add all video results",
        "ja": "すべての動画結果を追加",
    },
    "添加全部音乐结果": {
        "zh_TW": "新增全部音樂結果",
        "en": "Add all music results",
        "ja": "すべての音楽結果を追加",
    },
    "音乐": {
        "zh_TW": "音樂",
        "en": "Music",
        "ja": "音楽",
    },
    "未找到与「{}」相关的音乐视频": {
        "zh_TW": "未找到與「{}」相關的音樂影片",
        "en": "No music videos found for “{}”",
        "ja": "「{}」に関連する音楽動画が見つかりません",
    },
    "「{}」：{} 音乐视频": {
        "zh_TW": "「{}」：{} 音樂影片",
        "en": "“{}”: {} music videos",
        "ja": "「{}」：{} 音楽動画",
    },
    "关闭": {
        "zh_TW": "關閉",
        "en": "Close",
        "ja": "閉じる",
    },
    "未登录": {
        "zh_TW": "未登入",
        "en": "Not Logged In",
        "ja": "未ログイン",
    },
    "搜索需要登录（用于签名校验），请先登录。": {
        "zh_TW": "搜尋需要登入（用於簽章校驗），請先登入。",
        "en": "Search requires login (for signature verification). Please log in first.",
        "ja": "検索にはログインが必要です（署名検証用）。先にログインしてください。",
    },
    "正在搜索：{} …": {
        "zh_TW": "正在搜尋：{} …",
        "en": "Searching: {} …",
        "ja": "検索中: {} …",
    },
    "搜索异常：{}": {
        "zh_TW": "搜尋異常：{}",
        "en": "Search error: {}",
        "ja": "検索エラー: {}",
    },
    "未找到与「{}」相关的结果": {
        "zh_TW": "未找到與「{}」相關的結果",
        "en": "No results found for \"{}\"",
        "ja": "「{}」に関連する結果は見つかりませんでした",
    },
    "「{}」：{} 视频 / {} 番剧 / {} UP主": {
        "zh_TW": "「{}」：{} 影片 / {} 番劇 / {} UP主",
        "en": "{}: {} videos / {} bangumi / {} uploaders",
        "ja": "{}: 動画 {} / アニメ {} / 投稿者 {}",
    },
    "视频": {
        "zh_TW": "影片",
        "en": "Video",
        "ja": "動画",
    },
    "番剧": {
        "zh_TW": "番劇",
        "en": "Bangumi",
        "ja": "アニメ",
    },
    "UP主": {
        "zh_TW": "UP主",
        "en": "Uploader",
        "ja": "投稿者",
    },
    "添加": {
        "zh_TW": "新增",
        "en": "Add",
        "ja": "追加",
    },
    "打开TA的空间": {
        "zh_TW": "打開TA的空間",
        "en": "Open Their Space",
        "ja": "そのスペースを開く",
    },
    "已添加到下载队列": {
        "zh_TW": "已新增至下載佇列",
        "en": "Added to download queue",
        "ja": "ダウンロードキューに追加しました",
    },
    "正在解析番剧分集…": {
        "zh_TW": "正在解析番劇分集…",
        "en": "Parsing bangumi episodes…",
        "ja": "アニメのエピソードを解析中…",
    },
    "番剧解析失败：{}": {
        "zh_TW": "番劇解析失敗：{}",
        "en": "Bangumi parsing failed: {}",
        "ja": "アニメの解析に失敗: {}",
    },
    "该番剧没有可下载的分集": {
        "zh_TW": "該番劇沒有可下載的分集",
        "en": "This bangumi has no downloadable episodes",
        "ja": "このアニメにはダウンロード可能なエピソードがありません",
    },
    "已添加 {} 个番剧分集到下载队列": {
        "zh_TW": "已新增 {} 個番劇分集到下載佇列",
        "en": "Added {} bangumi episodes to download queue",
        "ja": "アニメのエピソード {} 件をダウンロードキューに追加",
    },
    "提示": {
        "zh_TW": "提示",
        "en": "Notice",
        "ja": "ヒント",
    },
    "下载正在进行中": {
        "zh_TW": "下載正在進行中",
        "en": "Download is already in progress",
        "ja": "ダウンロード実行中です",
    },
    "队列为空，请先添加视频": {
        "zh_TW": "佇列為空，請先新增影片",
        "en": "Queue is empty, add videos first",
        "ja": "キューが空です。まず動画を追加してください",
    },
    "下载进行中，无法清空队列": {
        "zh_TW": "下載進行中，無法清空佇列",
        "en": "Cannot clear queue while downloading",
        "ja": "ダウンロード中はキューをクリアできません",
    },
    "未找到 FFmpeg，无法合并音视频（可在「设置」中指定路径，或留空使用 bin/ffmpeg）": {
        "zh_TW": "未找到 FFmpeg，無法合併音視頻（可在「設定」中指定路徑，或留空使用 bin/ffmpeg）",
        "en": "FFmpeg not found, cannot merge audio/video (set its path in Settings, or leave empty to use bin/ffmpeg)",
        "ja": "FFmpeg が見つかりません。音声/映像を結合できません（「設定」でパスを指定するか、空欄にして bin/ffmpeg を使用）",
    },
    "链接解析失败，请确认输入的是有效的 B 站链接": {
        "zh_TW": "連結解析失敗，請確認輸入的是有效的 B 站連結",
        "en": "Link parsing failed, please make sure it is a valid Bilibili URL",
        "ja": "リンク解析に失敗しました。有効な Bilibili の URL か確認してください",
    },
    "无法通过搜索打开 UP 主空间": {
        "zh_TW": "無法透過搜尋開啟 UP 主空間",
        "en": "Cannot open the uploader's space via search",
        "ja": "検索から投稿者の空間を開けません",
    },
    "已添加 {} 个视频到下载队列": {
        "zh_TW": "已新增 {} 個影片到下載佇列",
        "en": "Added {} videos to download queue",
        "ja": "動画 {} 件をダウンロードキューに追加",
    },

    # ---------- video_select_dialog ----------
    "选择": {
        "zh_TW": "選擇",
        "en": "Select",
        "ja": "選択",
    },
    "标题": {
        "zh_TW": "標題",
        "en": "Title",
        "ja": "タイトル",
    },
    "来源": {
        "zh_TW": "來源",
        "en": "Source",
        "ja": "ソース",
    },
    "时长": {
        "zh_TW": "時長",
        "en": "Duration",
        "ja": "長さ",
    },
    "发布时间": {
        "zh_TW": "發佈時間",
        "en": "Published",
        "ja": "投稿日時",
    },
    "播放": {
        "zh_TW": "播放",
        "en": "Views",
        "ja": "再生",
    },
    "点赞": {
        "zh_TW": "點讚",
        "en": "Likes",
        "ja": "高評価",
    },
    "收藏": {
        "zh_TW": "收藏",
        "en": "Favorites",
        "ja": "お気に入り",
    },
    "选择下载视频": {
        "zh_TW": "選擇下載影片",
        "en": "Select Videos to Download",
        "ja": "ダウンロードする動画を選択",
    },
    "正在加载第 1 页…": {
        "zh_TW": "正在載入第 1 頁…",
        "en": "Loading page 1…",
        "ja": "ページ 1 を読み込み中…",
    },
    "总计 {} 个视频": {
        "zh_TW": "總計 {} 個影片",
        "en": "Total {} videos",
        "ja": "合計 {} 個の動画",
    },
    "搜索标题 / UP主 / 类型…": {
        "zh_TW": "搜尋標題 / UP主 / 類型…",
        "en": "Search title / uploader / type…",
        "ja": "タイトル / 投稿者 / タイプを検索…",
    },
    "上一页": {
        "zh_TW": "上一頁",
        "en": "Previous",
        "ja": "前へ",
    },
    "下一页": {
        "zh_TW": "下一頁",
        "en": "Next",
        "ja": "次へ",
    },
    "跳转页码：": {
        "zh_TW": "跳轉頁碼：",
        "en": "Go to page: ",
        "ja": "ページ移動: ",
    },
    "跳转": {
        "zh_TW": "跳轉",
        "en": "Jump",
        "ja": "移動",
    },
    "全选当前页": {
        "zh_TW": "全選當前頁",
        "en": "Select current page",
        "ja": "現在のページを全選択",
    },
    "全选全部": {
        "zh_TW": "全選全部",
        "en": "Select all",
        "ja": "すべて選択",
    },
    "全选已加载": {
        "zh_TW": "全選已載入",
        "en": "Select loaded",
        "ja": "読み込み済みを全選択",
    },
    "清空勾选": {
        "zh_TW": "清空勾選",
        "en": "Clear selection",
        "ja": "選択をクリア",
    },
    "添加选中到下载队列": {
        "zh_TW": "新增選中到下載佇列",
        "en": "Add selected to download queue",
        "ja": "選択項目をダウンロードキューに追加",
    },
    "第 {} / {} 页": {
        "zh_TW": "第 {} / {} 頁",
        "en": "Page {} / {}",
        "ja": "{} / {} ページ",
    },
    "（还有更多）": {
        "zh_TW": "（還有更多）",
        "en": "(more available)",
        "ja": "（さらにあり）",
    },
    "第 {} 页{}": {
        "zh_TW": "第 {} 頁{}",
        "en": "Page {}{}",
        "ja": "{} ページ{}",
    },
    "加载第 {} 页…": {
        "zh_TW": "載入第 {} 頁…",
        "en": "Loading page {}…",
        "ja": "ページ {} を読み込み中…",
    },
    "第 {} 页：{} 个视频": {
        "zh_TW": "第 {} 頁：{} 個影片",
        "en": "Page {}: {} videos",
        "ja": "{} ページ: 動画 {} 件",
    },
    " / 共 {} 页": {
        "zh_TW": " / 共 {} 頁",
        "en": " / {} pages total",
        "ja": " / 全 {} ページ",
    },
    "第 {} 页加载失败：{}": {
        "zh_TW": "第 {} 頁載入失敗：{}",
        "en": "Failed to load page {}: {}",
        "ja": "ページ {} の読み込み失敗: {}",
    },
    "请输入有效页码": {
        "zh_TW": "請輸入有效頁碼",
        "en": "Please enter a valid page number",
        "ja": "有効なページ番号を入力してください",
    },
    "未知": {
        "zh_TW": "未知",
        "en": "Unknown",
        "ja": "不明",
    },
    "（匹配 {}）": {
        "zh_TW": "（匹配 {}）",
        "en": "(matched {})",
        "ja": "（一致: {}）",
    },
    "请至少勾选一个视频": {
        "zh_TW": "請至少勾選一個影片",
        "en": "Please select at least one video",
        "ja": "少なくとも1つの動画を選択してください",
    },

    # ---------- episode_select_dialog（选集窗口） ----------
    "选择分集": {
        "zh_TW": "選擇分集",
        "en": "Select Episodes",
        "ja": "エピソードを選択",
    },
    "选择番剧分集": {
        "zh_TW": "選擇番劇分集",
        "en": "Select Bangumi Episodes",
        "ja": "番組エピソードを選択",
    },
    "全选": {
        "zh_TW": "全選",
        "en": "Select All",
        "ja": "すべて選択",
    },
    "搜索分集标题…": {
        "zh_TW": "搜尋分集標題…",
        "en": "Search episode title…",
        "ja": "エピソードタイトルを検索…",
    },
    "总计 {} 个分集": {
        "zh_TW": "總計 {} 個分集",
        "en": "Total {} episodes",
        "ja": "合計 {} エピソード",
    },

    # ---------- download_options_dialog ----------
    "下载选项": {
        "zh_TW": "下載選項",
        "en": "Download Options",
        "ja": "ダウンロード設定",
    },
    "已选择 {} 个视频 · 本次下载设置（确认后生效）": {
        "zh_TW": "已選擇 {} 個影片 · 本次下載設定（確認後生效）",
        "en": "{} videos selected · download settings (applied on confirm)",
        "ja": "動画 {} 件を選択 · 今回のダウンロード設定（確定で反映）",
    },
    "媒体设置": {
        "zh_TW": "媒體設定",
        "en": "Media",
        "ja": "メディア",
    },
    "附加文件": {
        "zh_TW": "附加檔案",
        "en": "Extra Files",
        "ja": "追加ファイル",
    },
    "下载设置": {
        "zh_TW": "下載設定",
        "en": "Download",
        "ja": "ダウンロード",
    },
    "取消": {
        "zh_TW": "取消",
        "en": "Cancel",
        "ja": "キャンセル",
    },
    "确认添加": {
        "zh_TW": "確認新增",
        "en": "Confirm Add",
        "ja": "追加を確定",
    },
    "清晰度:": {
        "zh_TW": "清晰度:",
        "en": "Quality:",
        "ja": "画質:",
    },
    "视频编码:": {
        "zh_TW": "視頻編碼:",
        "en": "Video codec:",
        "ja": "映像コーデック:",
    },
    "封装格式:": {
        "zh_TW": "封裝格式:",
        "en": "Container:",
        "ja": "コンテナ形式:",
    },
    "下载视频流": {
        "zh_TW": "下載影片流",
        "en": "Download video stream",
        "ja": "動画ストリームをダウンロード",
    },
    "下载音频流": {
        "zh_TW": "下載音訊流",
        "en": "Download audio stream",
        "ja": "音声ストリームをダウンロード",
    },
    "合并视频与音频为单个文件": {
        "zh_TW": "合併影片與音訊為單個檔案",
        "en": "Merge video and audio into a single file",
        "ja": "動画と音声を1つのファイルに結合",
    },
    "音画分离（视频与音频分别保存为独立文件）": {
        "zh_TW": "音畫分離（影片與音訊分別儲存為獨立檔案）",
        "en": "Separate audio/video (video and audio saved as separate files)",
        "ja": "音声と映像を分離（動画と音声を別ファイルで保存）",
    },
    "仅下载音频（不下载视频流）": {
        "zh_TW": "僅下載音訊（不下載影片流）",
        "en": "Audio only (no video stream)",
        "ja": "音声のみ（動画ストリームなし）",
    },
    "音频格式:": {
        "zh_TW": "音訊格式:",
        "en": "Audio format:",
        "ja": "音声形式:",
    },
    "音频格式仅在「音画分离」或「仅下载音频」时生效": {
        "zh_TW": "音訊格式僅在「音畫分離」或「僅下載音訊」時生效",
        "en": "Audio format applies only when audio/video is separated or audio-only",
        "ja": "音声形式は「音声分離」または「音声のみ」の場合のみ有効",
    },
    "下载弹幕": {
        "zh_TW": "下載彈幕",
        "en": "Download danmaku",
        "ja": "弾幕をダウンロード",
    },
    "格式:": {
        "zh_TW": "格式:",
        "en": "Format:",
        "ja": "形式:",
    },
    "下载字幕": {
        "zh_TW": "下載字幕",
        "en": "Download subtitles",
        "ja": "字幕をダウンロード",
    },
    "语言:": {
        "zh_TW": "語言:",
        "en": "Language:",
        "ja": "言語:",
    },
    "下载封面": {
        "zh_TW": "下載封面",
        "en": "Download cover",
        "ja": "カバーをダウンロード",
    },
    "将封面内嵌到视频文件（需开启下载封面）": {
        "zh_TW": "將封面內嵌到影片檔案（需開啟下載封面）",
        "en": "Embed cover into video file (requires download cover)",
        "ja": "カバーを動画ファイルに埋め込む（カバーDL要）",
    },
    "内嵌后删除原封面文件（需开启『内嵌封面』）": {
        "zh_TW": "內嵌後刪除原封面檔案（需開啟『內嵌封面』）",
        "en": "Delete original cover after embedding (requires 'Embed cover')",
        "ja": "埋め込み後に元のカバーファイルを削除（『カバー埋め込み』要）",
    },
    "保存元数据": {
        "zh_TW": "儲存元資料",
        "en": "Save metadata",
        "ja": "メタデータを保存",
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
    "下载限速 (KB/s, 0=不限):": {
        "zh_TW": "下載限速 (KB/s, 0=不限):",
        "en": "Download speed limit (KB/s, 0=unlimited):",
        "ja": "ダウンロード速度制限 (KB/s, 0=無制限):",
    },
    "并行下载数:": {
        "zh_TW": "並行下載數:",
        "en": "Parallel downloads:",
        "ja": "並列ダウンロード数:",
    },
    "同名文件处理:": {
        "zh_TW": "同名檔案處理:",
        "en": "Existing file handling:",
        "ja": "同名ファイルの処理:",
    },
    "auto_rename=自动重命名；overwrite=覆盖已存在文件": {
        "zh_TW": "auto_rename=自動重新命名；overwrite=覆蓋已存在檔案",
        "en": "auto_rename=auto rename; overwrite=overwrite existing file",
        "ja": "auto_rename=自動リネーム；overwrite=既存ファイルを上書き",
    },
    "为合集/多P视频创建单独文件夹": {
        "zh_TW": "為合集/多P影片建立單獨資料夾",
        "en": "Create separate folder for collections/multi-P videos",
        "ja": "コレクション/マルチP動画ごとにフォルダを作成",
    },
    "以后每次选择视频都弹出此对话框": {
        "zh_TW": "以後每次選擇影片都彈出此對話方塊",
        "en": "Always show this dialog when selecting videos",
        "ja": "動画選択時に毎回このダイアログを表示",
    },
    "无法开始": {
        "zh_TW": "無法開始",
        "en": "Cannot start",
        "ja": "開始できません",
    },
    "请至少选择下载视频流或音频流之一。": {
        "zh_TW": "請至少選擇下載影片流或音訊流之一。",
        "en": "Please select at least one of video or audio stream.",
        "ja": "動画ストリームか音声ストリームのいずれかを選択してください。",
    },
    "仅下载视频流会产生无声视频。\n如确需无音轨视频可继续，否则请同时开启音频流。": {
        "zh_TW": "僅下載影片流會產生無聲影片。\n如確需無音軌影片可繼續，否則請同時開啟音訊流。",
        "en": "Downloading video stream only produces a silent video.\nIf you really need a video without audio track, continue; otherwise enable the audio stream too.",
        "ja": "動画ストリームのみのダウンロードは無音動画になります。\n音声なし動画が必要な場合のみ続行、それ以外は音声ストリームも有効にしてください。",
    },
    "未开启「合并视频与音频」，将得到视频、音频两个独立文件。\n如需单个完整视频请开启合并。": {
        "zh_TW": "未開啟「合併影片與音訊」，將得到影片、音訊兩個獨立檔案。\n如需單個完整影片請開啟合併。",
        "en": "Merging video and audio is not enabled; you will get two separate files (video and audio).\nEnable merging for a single complete video.",
        "ja": "動画と音声の結合が無効です。動画と音声の2ファイルになります。\n1つの完全な動画にするには結合を有効にしてください。",
    },

    # ---------- following_dialog ----------
    "我的关注": {
        "zh_TW": "我的關注",
        "en": "My Following",
        "ja": "フォロー中",
    },
    "我的关注 · 共 {} 位UP主": {
        "zh_TW": "我的關注 · 共 {} 位UP主",
        "en": "My Following · {} uploaders",
        "ja": "フォロー中 · 投稿者 {} 名",
    },
    "搜索UP主昵称 / 签名…": {
        "zh_TW": "搜尋UP主暱稱 / 簽名…",
        "en": "Search uploader name / signature…",
        "ja": "投稿者名 / 署名を検索…",
    },
    "点击「打开TA的个人空间」浏览并下载该UP的视频": {
        "zh_TW": "點擊「打開TA的個人空間」瀏覽並下載該UP的影片",
        "en": "Click \"Open Their Space\" to browse and download this uploader's videos",
        "ja": "「そのスペースを開く」でこの投稿者の動画を閲覧・ダウンロード",
    },
    "未知UP主": {
        "zh_TW": "未知UP主",
        "en": "Unknown uploader",
        "ja": "不明な投稿者",
    },
    "打开TA的个人空间": {
        "zh_TW": "打開TA的個人空間",
        "en": "Open Their Personal Space",
        "ja": "その個人スペースを開く",
    },
    # ---------- 顺序选集（v2.2.0，多类型混合勾选） ----------
    "上一个": {
        "zh_TW": "上一個",
        "en": "Previous",
        "ja": "前へ",
    },
    "下一个": {
        "zh_TW": "下一個",
        "en": "Next",
        "ja": "次へ",
    },
    "分集视频 {i}/{n}": {
        "zh_TW": "分集影片 {i}/{n}",
        "en": "Episode video {i}/{n}",
        "ja": "エピソード動画 {i}/{n}",
    },
    "未勾选任何分集": {
        "zh_TW": "未勾選任何分集",
        "en": "No episodes selected",
        "ja": "エピソードが選択されていません",
    },
    "“{}”的个人空间": {
        "zh_TW": "「{}」的個人空間",
        "en": "{}'s Space",
        "ja": "「{}」の個人スペース",
    },
    "选择你想下载“{}”的分集": {
        "zh_TW": "選擇你想下載「{}」的分集",
        "en": "Select episodes of {} to download",
        "ja": "「{}」のエピソードを選択してダウンロード",
    },
    "未命名": {
        "zh_TW": "未命名",
        "en": "Untitled",
        "ja": "無題",
    },
    "UP主空间": {
        "zh_TW": "UP主空間",
        "en": "Uploader's Space",
        "ja": "UP主のスペース",
    },
    "用户协议": {
        "zh_TW": "使用者協議",
        "en": "User Agreement",
        "ja": "利用規約",
    },
    "请滚动阅读至底部后，方可同意": {
        "zh_TW": "請捲動閱讀至底部後，方可同意",
        "en": "Scroll to the bottom before agreeing",
        "ja": "同意するには末尾までスクロールしてください",
    },
    "不同意并退出": {
        "zh_TW": "不同意並結束",
        "en": "Disagree and Exit",
        "ja": "同意せず終了",
    },
    "同意并继续": {
        "zh_TW": "同意並繼續",
        "en": "Agree and Continue",
        "ja": "同意して続ける",
    },
    # ---------- 反馈页 ----------
    "反馈": {
        "zh_TW": "回饋",
        "en": "Feedback",
        "ja": "フィードバック",
    },
    "支持作者（自愿）": {
        "zh_TW": "支援作者（自願）",
        "en": "Support the Author (optional)",
        "ja": "作者を支援（任意）",
    },
    "Bug 反馈": {
        "zh_TW": "Bug 回饋",
        "en": "Report a Bug",
        "ja": "バグを報告",
    },
    "功能建议": {
        "zh_TW": "功能建議",
        "en": "Feature Request",
        "ja": "機能要望",
    },
    "反馈与建议": {
        "zh_TW": "回饋與建議",
        "en": "Feedback & Suggestions",
        "ja": "フィードバックと提案",
    },
    "填写反馈后将在浏览器打开已填好的 GitHub 议题页，确认无误点发布即可。内容会先存为本地草稿，中途离开不会丢失。": {
        "zh_TW": "填寫回饋後將在瀏覽器開啟已填好的 GitHub 議題頁，確認無誤點釋出即可。內容會先存為本機草稿，中途離開不會遺失。",
        "en": "After filling in the feedback, a pre-filled GitHub issue page will open in your browser—just confirm and submit. Your input is auto-saved as a local draft.",
        "ja": "入力後、記入済みのGitHubイシューページがブラウザで開きます。内容はローカル下書きとして自動保存されます。",
    },
    "一句话概括你的问题或建议": {
        "zh_TW": "一句話概括你的問題或建議",
        "en": "Summarize your issue or suggestion in one line",
        "ja": "問題や提案を一行で要約",
    },
    "请详细描述：问题现象 / 复现步骤 / 期望结果，或建议的使用场景与方案": {
        "zh_TW": "請詳細描述：問題現象 / 重現步驟 / 預期結果，或建議的使用情境與方案",
        "en": "Describe in detail: what happened / steps to reproduce / expected result, or the use case and solution of your suggestion",
        "ja": "詳細に記述してください：発生内容 / 再現手順 / 期待結果、または提案の利用場面と方案",
    },
    "将自动附带环境信息：": {
        "zh_TW": "將自動附上環境資訊：",
        "en": "Environment info will be attached automatically: ",
        "ja": "環境情報は自動的に添付されます：",
    },
    "提交反馈": {
        "zh_TW": "提交回饋",
        "en": "Submit Feedback",
        "ja": "フィードバックを送信",
    },
    "清空草稿": {
        "zh_TW": "清空草稿",
        "en": "Clear Draft",
        "ja": "下書きを消去",
    },
    "草稿已自动保存": {
        "zh_TW": "草稿已自動儲存",
        "en": "Draft auto-saved",
        "ja": "下書きを自動保存しました",
    },
    "草稿保存失败（不影响提交）": {
        "zh_TW": "草稿儲存失敗（不影響提交）",
        "en": "Draft save failed (does not affect submission)",
        "ja": "下書きの保存に失敗（送信には影響しません）",
    },
    "已恢复上次的草稿": {
        "zh_TW": "已還原上次的草稿",
        "en": "Restored your last draft",
        "ja": "前回の下書きを復元しました",
    },
    "草稿已清空": {
        "zh_TW": "草稿已清空",
        "en": "Draft cleared",
        "ja": "下書きを消去しました",
    },
    "反馈信息不完整": {
        "zh_TW": "回饋資訊不完整",
        "en": "Incomplete feedback",
        "ja": "フィードバックの情報が不足しています",
    },
    "请填写标题和详细内容后再提交": {
        "zh_TW": "請填寫標題和詳細內容後再提交",
        "en": "Please fill in the title and details before submitting",
        "ja": "送信する前にタイトルと詳細を入力してください",
    },
    "即将提交反馈": {
        "zh_TW": "即將提交回饋",
        "en": "Submitting Feedback",
        "ja": "フィードバックを送信中",
    },
    "已在浏览器打开发布页面，确认无误后点击 Submit new issue 即可。你的反馈进入公开议题区后，会由 AI 预筛 + 维护者审核决定是否采纳。": {
        "zh_TW": "已在瀏覽器開啟釋出頁面，確認無誤後點擊 Submit new issue 即可。你的回饋進入公開議題區後，會由 AI 預篩 + 維護者審核決定是否採納。",
        "en": "The publish page is open in your browser; confirm and click 'Submit new issue'. Once public, your feedback is AI-pre-screened and reviewed by maintainers for acceptance.",
        "ja": "公開ページがブラウザで開きました。確認して「Submit new issue」をクリックしてください。公開後はAI予選とメンテナーの審査で採否が決まります。",
    },
    "正在提交反馈...": {
        "zh_TW": "正在提交回饋...",
        "en": "Submitting feedback...",
        "ja": "フィードバックを送信中...",
    },
    "提交成功": {
        "zh_TW": "提交成功",
        "en": "Submitted",
        "ja": "送信完了",
    },
    "反馈已提交：": {
        "zh_TW": "回饋已提交：",
        "en": "Feedback submitted: ",
        "ja": "フィードバックを送信しました：",
    },
    "反馈已成功提交，感谢你的支持！": {
        "zh_TW": "回饋已成功提交，感謝你的支援！",
        "en": "Feedback submitted successfully. Thanks for your support!",
        "ja": "フィードバックを送信しました。ご協力ありがとうございます！",
    },
    "代理提交失败，已改为打开浏览器发布页": {
        "zh_TW": "代理提交失敗，已改為開啟瀏覽器釋出頁",
        "en": "Proxy submission failed; opened the browser publish page instead",
        "ja": "プロキシ送信に失敗したため、ブラウザの公開ページを開きました",
    },
}
