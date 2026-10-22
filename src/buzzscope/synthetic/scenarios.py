"""Synthetic scenarios with planted events (the ground truth for evaluation).

All brands here are FICTIONAL. Using made-up brands avoids publishing invented
negative "events" about real companies.

Each scenario = 90 days of everyday discussion + a few planted events that cause
volume spikes, plus "decoy" spikes where the brand's short name appears in an
unrelated context (e.g. 晨光 = morning light in a photography thread). A good
analyst should explain the real events and flag the decoys as irrelevant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

END_DATE = date(2026, 10, 15)
N_DAYS = 90
START_DATE = END_DATE - timedelta(days=N_DAYS - 1)


@dataclass
class EventSpec:
    id: str
    day: int  # offset from START_DATE
    profile: list[int]  # extra posts per day starting at `day`
    sentiment: str  # gold sentiment: positive / negative
    cause: str  # human description of the planted cause
    aliases: list[str]  # any of these in the analyst's cause text counts as correct
    titles: list[str]
    sentences: list[str]
    comments: list[tuple[str, str]]
    boards: list[str]
    relevant: bool = True

    @property
    def date(self) -> date:
        return START_DATE + timedelta(days=self.day)


@dataclass
class Scenario:
    key: str
    entity: str
    short_name: str
    example_question: str
    boards: list[str]
    base_rate: float
    items: list[str]
    places: list[str]
    base_titles: list[str]
    pos_sentences: list[str]
    neg_sentences: list[str]
    neu_sentences: list[str]
    pos_comments: list[tuple[str, str]]
    neg_comments: list[tuple[str, str]]
    neu_comments: list[tuple[str, str]]
    events: list[EventSpec] = field(default_factory=list)

    @property
    def gold_events(self) -> list[EventSpec]:
        return [e for e in self.events if e.relevant]

    @property
    def decoys(self) -> list[EventSpec]:
        return [e for e in self.events if not e.relevant]


FILLERS = ["以上個人心得，供大家參考。", "大家覺得呢？", "有錯請指正。", "純分享。", "", ""]
GENERIC_NEU_COMMENTS = [("→", "路過"), ("→", "看分店吧"), ("→", "每個人口味不同"), ("→", "先收藏")]


COFFEE = Scenario(
    key="coffee",
    entity="晨光咖啡",
    short_name="晨光",
    example_question="最近大家怎麼看晨光咖啡？",
    boards=["Food", "Coffee", "Lifeismoney"],
    base_rate=6.0,
    items=["拿鐵", "美式", "焦糖瑪奇朵", "燕麥拿鐵", "冷萃咖啡", "可頌"],
    places=["中壢", "桃園", "板橋", "信義", "西屯", "新竹"],
    base_titles=[
        "[心得] {e}{item}",
        "[問題] {e}哪個品項推薦？",
        "[閒聊] 每天早上一杯{e}",
        "[比較] {e}跟超商咖啡差在哪",
        "[心得] {e}{place}店",
        "[食記] {place} {e}早午餐",
    ],
    pos_sentences=[
        "{item}香氣很足，苦味不會太重，整體很順口。",
        "店員很親切，出餐速度也很快。",
        "會員點數累積起來滿划算的。",
        "座位寬敞，適合帶電腦來工作。",
        "價格合理，CP值不錯。",
        "{place}店環境很乾淨，音樂也不吵。",
    ],
    neg_sentences=[
        "今天的{item}有點太酸，跟平常差很多。",
        "排隊排了二十分鐘，有點誇張。",
        "座位很少，假日根本找不到位子。",
        "價格偏貴，不太划算。",
        "{place}店的店員態度有點冷淡。",
    ],
    neu_sentences=[
        "最近常去{place}店買早餐。",
        "想問大家平常都點什麼？",
        "聽說之後會推季節限定。",
        "今天下雨所以人比較少。",
        "我通常是外帶居多。",
    ],
    pos_comments=[
        ("推", "我也很愛他們的拿鐵"),
        ("推", "店員真的都很親切"),
        ("推", "CP值高"),
        ("推", "好喝推"),
    ],
    neg_comments=[
        ("噓", "太貴了吧"),
        ("噓", "排隊排到不想喝"),
        ("→", "最近品質有點不穩"),
        ("噓", "服務很差"),
    ],
    neu_comments=[("→", "我都點美式"), ("→", "我通常去超商")],
    events=[
        EventSpec(
            id="coffee_ice",
            day=25,
            profile=[26, 18, 10, 5],
            sentiment="negative",
            cause="衛生局抽驗發現門市冰塊大腸桿菌超標（食安事件）",
            aliases=["大腸桿菌", "冰塊", "抽驗", "食安"],
            titles=[
                "[新聞] 衛生局抽驗 {e}冰塊大腸桿菌超標",
                "[問卦] {e}冰塊驗出大腸桿菌？",
                "[討論] {e}冰塊不合格還敢喝嗎",
                "[心得] 看到{e}冰塊新聞嚇到",
            ],
            sentences=[
                "衛生局公布最新抽驗結果，{e}多家門市的冰塊大腸桿菌超標。",
                "業者表示已經全面更換製冰機濾心並加強清潔。",
                "昨天才剛喝完冰拿鐵，看到新聞整個傻眼。",
                "食安問題真的很難讓人放心。",
                "之後點飲料都改去冰好了。",
                "官方聲明說會配合複驗，但消費者信心已經受影響。",
            ],
            comments=[
                ("噓", "噁心"),
                ("噓", "冰塊都能出問題"),
                ("噓", "再也不買了"),
                ("→", "其他家也不一定比較好"),
                ("噓", "食安又來了"),
                ("→", "等複驗結果吧"),
                ("推", "至少有出來道歉"),
            ],
            boards=["Food", "Gossiping"],
        ),
        EventSpec(
            id="coffee_decoy_sunrise",
            day=40,
            profile=[22, 15, 6],
            sentiment="positive",
            cause="合歡山晨光攝影討論（與品牌無關）",
            aliases=["合歡山", "攝影", "日出", "雲海"],
            titles=["[作品] 合歡山的晨光", "[分享] 連假追晨光 雲海超壯觀", "[問題] 拍晨光要幾點上山？"],
            sentences=[
                "連假上合歡山拍晨光，雲海加上日出真的超震撼。",
                "凌晨三點出發，四點半就開始卡位。",
                "晨光灑在山稜線上的那一刻值回票價。",
                "建議帶腳架和保暖外套。",
                "下次想挑戰武嶺拍銀河。",
            ],
            comments=[
                ("推", "好美"),
                ("推", "構圖很棒"),
                ("推", "雲海太讚"),
                ("→", "人好多"),
                ("推", "收藏"),
            ],
            boards=["DSLR", "Hiking"],
            relevant=False,
        ),
        EventSpec(
            id="coffee_collab",
            day=52,
            profile=[30, 22, 12, 6],
            sentiment="positive",
            cause="與人氣動畫聯名杯套開賣，多間門市秒殺",
            aliases=["聯名", "杯套", "動畫"],
            titles=[
                "[情報] {e} x 人氣動畫聯名杯套開賣",
                "[心得] 排了一小時終於買到{e}聯名杯套",
                "[問題] {e}聯名杯套哪間店還有？",
                "[閒聊] {e}聯名也太可愛",
            ],
            sentences=[
                "{e}跟人氣動畫的聯名杯套今天開賣，好幾間門市一早就賣光。",
                "杯套設計超可愛，買一杯送一個隨機款。",
                "官網說明下週會補貨。",
                "為了集滿全套已經喝了五杯。",
                "聯名周邊在網拍被炒到原價三倍。",
            ],
            comments=[
                ("推", "超可愛"),
                ("推", "已收全套"),
                ("推", "排隊也值得"),
                ("→", "網拍炒價很誇張"),
                ("推", "求補貨"),
                ("推", "行銷做得很好"),
            ],
            boards=["Food", "Lifeismoney"],
        ),
        EventSpec(
            id="coffee_app",
            day=74,
            profile=[13, 9, 4],
            sentiment="negative",
            cause="App 當機導致買一送一優惠券無法使用",
            aliases=["App", "當機", "優惠券", "買一送一"],
            titles=[
                "[抱怨] {e} App 當機 買一送一優惠券不能用",
                "[問題] {e}優惠券一直顯示錯誤？",
                "[閒聊] {e} App 又當機了",
            ],
            sentences=[
                "今天是買一送一活動最後一天，結果{e} App 一直當機。",
                "優惠券頁面一直轉圈圈，在櫃檯卡了十分鐘。",
                "客服只說系統異常，請稍後再試。",
                "活動辦了系統卻撐不住，很傷。",
                "後來官方宣布活動延長三天作為補償。",
            ],
            comments=[
                ("噓", "工程師在幹嘛"),
                ("噓", "白跑一趟"),
                ("→", "延長三天還可以"),
                ("噓", "每次活動都當"),
                ("→", "我剛剛用成功了"),
            ],
            boards=["Lifeismoney", "Food"],
        ),
    ],
)


TEA = Scenario(
    key="tea",
    entity="拾光茶飲",
    short_name="拾光",
    example_question="拾光茶飲最近的網路風向如何？",
    boards=["Drink", "Food", "Lifeismoney"],
    base_rate=7.0,
    items=["珍珠奶茶", "四季春", "鮮奶茶", "冬瓜檸檬", "芋頭鮮奶", "烏龍綠"],
    places=["中壢", "台中", "高雄", "台南", "新莊", "三重"],
    base_titles=[
        "[心得] {e}{item}",
        "[問題] {e}甜度怎麼點？",
        "[閒聊] {e}必點清單",
        "[比較] {e}跟其他手搖差在哪",
        "[心得] {e}{place}門市",
    ],
    pos_sentences=[
        "{item}茶味很香，甜度也剛好。",
        "珍珠Q彈，口感很好。",
        "店員會主動提醒大杯比較划算，很貼心。",
        "價格親民，學生也喝得起。",
        "{place}門市出杯很快，不用等太久。",
    ],
    neg_sentences=[
        "{item}茶味太淡，喝起來像水。",
        "等了快半小時才拿到飲料。",
        "這次的珍珠有點硬。",
        "冰塊放太多，喝沒幾口就沒了。",
    ],
    neu_sentences=[
        "想問大家微糖跟半糖差多少？",
        "最近天氣熱，每天都想喝一杯。",
        "公司附近剛好有一間。",
        "聽說{place}要開新門市。",
    ],
    pos_comments=[("推", "四季春必點"), ("推", "珍珠真的好吃"), ("推", "便宜大碗")],
    neg_comments=[("噓", "茶味很淡"), ("噓", "等超久"), ("→", "品質看店")],
    neu_comments=[("→", "我都喝無糖"), ("→", "我比較喜歡別家")],
    events=[
        EventSpec(
            id="tea_price",
            day=18,
            profile=[20, 14, 7, 3],
            sentiment="negative",
            cause="宣布全品項每杯漲價 5 元",
            aliases=["漲價", "調漲", "5元", "五元"],
            titles=[
                "[新聞] {e}宣布全品項漲價5元",
                "[討論] {e}漲價還會繼續喝嗎",
                "[閒聊] 感謝{e}漲價 讓我戒手搖成功",
                "[閒聊] {e}佛心公司又來了",
            ],
            sentences=[
                "{e}宣布下週起全品項每杯調漲5元，理由是原物料和人事成本上升。",
                "一杯珍奶快要70元，學生真的喝不起。",
                "漲價可以理解，但品質要跟上。",
                "身邊同學已經說要改喝其他家。",
                "真是太感謝了，多虧{e}漲價，我的荷包跟體重都很滿意。",
                "佛心公司，連漲兩次還說是回饋顧客，值得鼓勵。",
            ],
            comments=[
                ("噓", "又漲"),
                ("噓", "喝不起了"),
                ("→", "大家都在漲"),
                ("噓", "掰掰"),
                ("→", "成本真的有上升吧"),
                ("推", "推佛心公司 漲得好"),
                ("推", "感謝幫我戒糖 太讚了"),
                ("推", "漲價也是一種成功"),
            ],
            boards=["Drink", "Lifeismoney"],
        ),
        EventSpec(
            id="tea_expired",
            day=60,
            profile=[28, 20, 11, 5],
            sentiment="negative",
            cause="前員工爆料門市使用過期茶葉",
            aliases=["過期", "茶葉", "爆料"],
            titles=[
                "[爆卦] 前員工爆料{e}用過期茶葉",
                "[新聞] {e}遭爆使用過期茶葉 業者回應了",
                "[討論] {e}過期茶葉事件大家怎麼看",
            ],
            sentences=[
                "有前員工在社群爆料，{e}部分門市會把過期茶葉重新貼標使用。",
                "業者回應已啟動內部調查，並將相關門市暫停營業。",
                "如果是真的也太可怕，每天都在喝。",
                "衛生單位表示會進行稽查。",
                "現在只敢喝連鎖大品牌了，結果大品牌也出事。",
            ],
            comments=[
                ("噓", "太扯了"),
                ("噓", "退坑"),
                ("噓", "貼標也太誇張"),
                ("→", "等調查結果"),
                ("噓", "難怪最近喝起來怪怪的"),
                ("推", "勇敢的員工"),
            ],
            boards=["Drink", "Gossiping"],
        ),
        EventSpec(
            id="tea_taro",
            day=80,
            profile=[24, 17, 9, 4],
            sentiment="positive",
            cause="新品黑糖芋頭鮮奶上市後爆紅",
            aliases=["黑糖芋頭", "新品", "芋頭"],
            titles=[
                "[心得] {e}新品黑糖芋頭鮮奶",
                "[閒聊] {e}黑糖芋頭也太好喝",
                "[問題] {e}黑糖芋頭鮮奶要排多久",
            ],
            sentences=[
                "{e}這次的新品黑糖芋頭鮮奶真的好喝，芋泥綿密不會太甜。",
                "黑糖香氣跟芋頭很搭，我已經回購三次。",
                "下午去買排了二十分鐘，很多人都是衝新品來的。",
                "社群上一堆人在分享開箱照。",
            ],
            comments=[
                ("推", "超好喝"),
                ("推", "芋頭控必喝"),
                ("推", "已回購"),
                ("→", "有點太甜"),
                ("推", "新品這次成功"),
            ],
            boards=["Drink", "Food"],
        ),
    ],
)


PHONE = Scenario(
    key="phone",
    entity="雲豹手機",
    short_name="雲豹",
    example_question="雲豹手機最近在網路上的評價怎麼樣？",
    boards=["MobileComm", "Android"],
    base_rate=5.0,
    items=["拍照", "續航", "螢幕", "充電速度", "系統更新", "散熱"],
    places=["台北", "台中", "高雄"],
    base_titles=[
        "[心得] {e}X8 使用一個月",
        "[問題] {e}{item}表現如何？",
        "[閒聊] {e}值得買嗎",
        "[比較] {e}跟其他中階機",
    ],
    pos_sentences=[
        "{item}表現超乎預期，這價位很難挑剔。",
        "系統很乾淨，沒有太多預載App。",
        "電池一天一充沒問題。",
        "手感很好，重量剛好。",
    ],
    neg_sentences=[
        "{item}普普通通，晚上拍照雜訊很多。",
        "玩遊戲會有點燙。",
        "系統更新後偶爾會卡頓。",
        "客服回覆很慢。",
    ],
    neu_sentences=[
        "考慮換機中，想問大家意見。",
        "預算一萬五左右。",
        "主要用途是拍照跟社群。",
        "最近門市好像在做活動。",
    ],
    pos_comments=[("推", "CP值機"), ("推", "我也在用很滿意"), ("推", "拍照真的不錯")],
    neg_comments=[("噓", "品控不穩"), ("→", "散熱是硬傷"), ("噓", "客服很爛")],
    neu_comments=[("→", "看預算"), ("→", "可以等新機")],
    events=[
        EventSpec(
            id="phone_launch",
            day=20,
            profile=[22, 15, 8, 4],
            sentiment="positive",
            cause="X9 新機發表會，定價低於預期",
            aliases=["發表", "定價", "X9", "新機"],
            titles=[
                "[情報] {e}X9 發表會 定價公布",
                "[討論] {e}X9 這個定價很有誠意",
                "[問題] {e}X9 值得首發嗎",
            ],
            sentences=[
                "{e}今天舉辦X9發表會，定價比大家預期便宜兩千元。",
                "規格升級不少，主鏡頭換了新感光元件。",
                "這個定價對其他品牌壓力很大。",
                "已經預購了，等開箱。",
            ],
            comments=[
                ("推", "定價佛心"),
                ("推", "預購了"),
                ("推", "規格很香"),
                ("→", "等實測"),
                ("推", "這次誠意十足"),
            ],
            boards=["MobileComm"],
        ),
        EventSpec(
            id="phone_decoy_leopard",
            day=33,
            profile=[18, 12, 5],
            sentiment="positive",
            cause="臺灣雲豹保育相關討論（與品牌無關）",
            aliases=["保育", "動物", "紅外線相機", "森林"],
            titles=[
                "[新聞] 研究團隊架設紅外線相機 尋找臺灣雲豹蹤跡",
                "[討論] 臺灣雲豹真的還存在嗎",
                "[閒聊] 雲豹保育紀錄片好好看",
            ],
            sentences=[
                "研究團隊在中央山脈架設紅外線相機，持續調查雲豹是否仍有族群。",
                "雲豹是臺灣森林生態很重要的指標物種。",
                "紀錄片拍到很多珍貴的森林動物畫面。",
                "希望保育工作能持續下去。",
            ],
            comments=[("推", "保育加油"), ("推", "希望還在"), ("推", "紀錄片推"), ("→", "機率很低吧")],
            boards=["Gossiping", "Nature"],
            relevant=False,
        ),
        EventSpec(
            id="phone_green_line",
            day=45,
            profile=[30, 22, 13, 6],
            sentiment="negative",
            cause="X9 螢幕出現綠線災情",
            aliases=["綠線", "螢幕"],
            titles=[
                "[災情] {e}X9 螢幕出現綠線",
                "[問題] {e}X9 綠線送修要多久",
                "[討論] {e}綠線災情越來越多",
            ],
            sentences=[
                "用不到兩個月，{e}X9 螢幕突然出現一條綠線。",
                "網路上已經有幾十個人回報同樣的螢幕綠線問題。",
                "送修說要等三週，期間沒有備用機。",
                "首發買的人真的很衰。",
            ],
            comments=[
                ("噓", "品控爛"),
                ("噓", "又是綠線"),
                ("→", "我也中了"),
                ("噓", "不敢買了"),
                ("→", "等官方回應"),
                ("噓", "首發當白老鼠"),
            ],
            boards=["MobileComm", "Android"],
        ),
        EventSpec(
            id="phone_repair",
            day=66,
            profile=[14, 10, 5],
            sentiment="positive",
            cause="官方宣布 X9 綠線免費換螢幕並延長保固",
            aliases=["免費換", "延長保固", "換螢幕", "保固"],
            titles=[
                "[情報] {e}宣布X9綠線免費換螢幕",
                "[心得] {e}免費換螢幕體驗",
                "[討論] {e}延長保固算有誠意嗎",
            ],
            sentences=[
                "{e}官方宣布X9綠線問題一律免費換螢幕，並延長保固一年。",
                "今天去換完螢幕，大概一小時就好。",
                "這個處理方式比很多大廠都有誠意。",
                "希望之後品控可以更穩定。",
            ],
            comments=[("推", "處理得不錯"), ("推", "有誠意"), ("推", "已換好"), ("→", "早該這樣")],
            boards=["MobileComm"],
        ),
    ],
)


SCENARIOS: dict[str, Scenario] = {s.key: s for s in (COFFEE, TEA, PHONE)}
