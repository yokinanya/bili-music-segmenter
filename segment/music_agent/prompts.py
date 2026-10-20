SCAN_PROMPT = """你是保守的直播歌切分析器。逐段检查当前音频核心区间，输出真正值得复核的音乐候选，不要逐秒转写。
候选分类：host_singing（主播清唱、主唱或能辨认出主播声音的跟唱）、background_music_chat（录音/背景音乐播放，主播聊天）、mixed_singing_and_chat（主播演唱与聊天交错）、uncertain（无法判断）。
背景录音里有歌声不代表主播在唱；只有听到主播本人清晰、持续的演唱才将 host_singing_present 设为 true。
极短哼声、聊天时放歌不得作为歌切候选。时间范围应覆盖音乐/演唱内容并排除明显聊天；不确定边界宁可收窄。
所有时间相对本次输入音频起点，重点分析给定核心范围，前后音频只作上下文。
只输出 JSON：
{"segments":[{"start_seconds":0.0,"end_seconds":120.0,"classification":"host_singing|background_music_chat|mixed_singing_and_chat|uncertain","confidence":0.0,"host_singing_present":true,"title_hint":"可明确听出的歌名，否则留空","rationale":"简述人声归属和边界依据"}]}
只返回起点落在核心范围的候选。没有可用音乐候选时 segments 返回空数组。"""

BOUNDARY_PROMPT = """你是高精度直播歌切边界复核器。判断目标范围内是否有主播本人清晰演唱。
清唱、卡拉OK伴奏、能分辨主播声音的跟唱均算；背景录音中的原唱、主播聊天、游戏声、极短哼声不算主播演唱。
前后附加音频是上下文，只用于分辨主播声音和确定真实首尾。只输出主播本人明确演唱的准确子区间，排除聊天、原唱独唱和纯器乐；宁可漏切，不可把聊天/背景音乐切进去。
时间为输入音频起点后的秒数。
只输出 JSON：
{"host_singing_present":true,"confidence":0.0,"intervals":[{"start_seconds":1.0,"end_seconds":50.0}],"rationale":"声学证据"}
若不能确认主播本人在唱，host_singing_present=false 且 intervals=[]。"""

TITLE_PROMPT = """两个音乐识别服务给出了不同结果。结合现场录音辨认出的歌词和主播说明，判断哪一项更可能是同一首作品。
繁简字差异、版本附注、括号中的影视剧名不应被视为不同歌曲；艺人可能是原唱、翻唱者或上传者。
你只能从候选中选，不得创造新歌名。证据不足选 unresolved。
只输出 JSON：{"choice":"shazam|netease|unresolved","confidence":0.0,"rationale":"简述依据"}"""
