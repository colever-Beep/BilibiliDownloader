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
}
