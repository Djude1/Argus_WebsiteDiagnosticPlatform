"""
網站內容模型：每個頁面/區塊一個 Singleton 模型，後台管理員透過表單欄位直接編輯
"""
from django.db import models


# ── 基礎 Singleton 模型 ─────────────────────────────────────────

class SingletonModel(models.Model):
    """單例模型基礎類別：每個子類別只允許一筆資料"""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # 禁止刪除

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# ── 全站設定 ─────────────────────────────────────────────────────

class SiteSettings(SingletonModel):
    """品牌、導覽列、頁尾等全站共用設定"""

    # 品牌
    brand_short = models.CharField('品牌縮寫', max_length=10, default='AI',
                                   help_text='顯示在 Logo 圖示中的文字')
    brand_name = models.CharField('品牌名稱', max_length=50, default='智慧眼鏡',
                                  help_text='Logo 旁邊的品牌文字')
    brand_description = models.TextField('品牌描述', default='結合 OpenAI GPT 語音助理與 AR 導航技術的次世代智慧穿戴裝置。基於開源專案 OpenAIglasses_for_Navigation 進行開發。',
                                         help_text='頁尾品牌區域的說明文字')

    # 導覽列
    nav_home = models.CharField('導覽：首頁', max_length=20, default='首頁')
    nav_product = models.CharField('導覽：產品介紹', max_length=20, default='產品介紹')
    nav_download = models.CharField('導覽：APP 下載', max_length=20, default='APP 下載')
    nav_purchase = models.CharField('導覽：立即購買', max_length=20, default='立即購買')
    nav_team = models.CharField('導覽：關於團隊', max_length=20, default='關於團隊')
    nav_admin = models.CharField('導覽：後台管理', max_length=20, default='後台管理')

    # 頁尾
    footer_quick_links_title = models.CharField('頁尾：快速連結標題', max_length=30, default='快速連結')
    footer_opensource_title = models.CharField('頁尾：開源資源標題', max_length=30, default='開源資源')
    footer_opensource_text = models.CharField('頁尾：原始專案連結文字', max_length=50, default='原始開源專案')
    footer_opensource_url = models.URLField('頁尾：原始專案 URL', max_length=300,
                                            default='https://github.com/AI-FanGe/OpenAIglasses_for_Navigation')
    footer_copyright = models.TextField('頁尾：版權聲明',
                                        default='2025 AI 導航智慧眼鏡專題。基於 OpenAIglasses_for_Navigation 開源專案。',
                                        help_text='年份與版權文字，前方會自動加上 (C) 符號')

    class Meta:
        verbose_name = '全站設定'
        verbose_name_plural = '全站設定'

    def __str__(self):
        return '全站設定'


# ── 首頁 ─────────────────────────────────────────────────────────

class HomeContent(SingletonModel):
    """首頁所有可編輯內容"""

    # Hero 區塊
    hero_badge = models.CharField('Hero 標籤文字', max_length=100,
                                  default='基於 OpenAIglasses_for_Navigation 開源專案')
    hero_title_1 = models.CharField('Hero 主標題第一行', max_length=50, default='AI 導航',
                                    help_text='白色文字')
    hero_title_2 = models.CharField('Hero 主標題第二行', max_length=50, default='智慧眼鏡',
                                    help_text='漸層色文字')
    hero_description = models.TextField('Hero 說明文字',
                                        default='將 OpenAI GPT 語音助理與 AR 擴增實境導航融合於一副輕巧眼鏡之中，讓您在行走間輕鬆獲取路線指引、AI 問答、環境資訊，開啟次世代穿戴體驗。')
    hero_btn_buy = models.CharField('Hero 購買按鈕文字', max_length=30, default='立即購買',
                                    help_text='價格會自動帶入')
    hero_btn_detail = models.CharField('Hero 詳情按鈕文字', max_length=30, default='查看產品詳情')
    model_hint = models.CharField('3D 模型操作提示', max_length=100, default='拖曳旋轉 · 滾輪縮放')

    # 統計數字
    stat_1_value = models.CharField('統計 1 數值', max_length=20, default='45g')
    stat_1_label = models.CharField('統計 1 標籤', max_length=20, default='超輕鏡框')
    stat_2_value = models.CharField('統計 2 數值', max_length=20, default='8h')
    stat_2_label = models.CharField('統計 2 標籤', max_length=20, default='續航時間')
    stat_3_value = models.CharField('統計 3 數值', max_length=20, default='GPT')
    stat_3_label = models.CharField('統計 3 標籤', max_length=20, default='AI 核心')

    # 特色亮點區塊
    features_title = models.CharField('特色亮點標題', max_length=100, default='為什麼選擇 AI 智慧眼鏡？')
    features_subtitle = models.TextField('特色亮點副標題',
                                         default='整合最先進的 AI 技術，讓穿戴科技真正融入您的日常生活。')

    # CTA 區塊
    cta_title = models.CharField('CTA 標題', max_length=100, default='準備好體驗 AI 穿戴未來了嗎？')
    cta_description = models.TextField('CTA 說明文字',
                                       default='現在訂購享有早鳥優惠，限時特惠中。',
                                       help_text='價格資訊會自動帶入')
    cta_btn_buy = models.CharField('CTA 購買按鈕', max_length=30, default='立即訂購')
    cta_btn_more = models.CharField('CTA 了解更多按鈕', max_length=30, default='了解更多')

    class Meta:
        verbose_name = '首頁內容'
        verbose_name_plural = '首頁內容'

    def __str__(self):
        return '首頁內容'


# ── 產品介紹頁 ───────────────────────────────────────────────────

class ProductPageContent(SingletonModel):
    """產品介紹頁所有可編輯內容"""

    back_link = models.CharField('返回首頁文字', max_length=20, default='返回首頁')
    model_hint = models.CharField('3D 模型操作提示', max_length=100, default='可互動 3D 預覽 · 拖曳旋轉 · 滾輪縮放')
    availability = models.CharField('庫存狀態文字', max_length=50, default='現貨供應中')
    btn_buy = models.CharField('購買按鈕文字', max_length=30, default='立即購買')
    tab_features = models.CharField('Tab：功能特點', max_length=20, default='功能特點')
    tab_specs = models.CharField('Tab：技術規格', max_length=20, default='技術規格')
    tab_description = models.CharField('Tab：詳細說明', max_length=20, default='詳細說明')
    empty_features = models.CharField('功能特點載入提示', max_length=50, default='功能特點資料載入中...')
    empty_specs = models.CharField('技術規格載入提示', max_length=50, default='技術規格資料載入中...')

    class Meta:
        verbose_name = '產品介紹頁'
        verbose_name_plural = '產品介紹頁'

    def __str__(self):
        return '產品介紹頁內容'


# ── APP 下載頁 ───────────────────────────────────────────────────

class DownloadPageContent(SingletonModel):
    """APP 下載頁所有可編輯內容"""

    # Hero
    hero_badge = models.CharField('Hero 標籤文字', max_length=100, default='Android APP 現已開放下載')
    hero_title_1 = models.CharField('Hero 主標題第一行', max_length=50, default='配套 APP')
    hero_title_2 = models.CharField('Hero 主標題第二行', max_length=50, default='解鎖眼鏡完整功能')
    hero_description = models.TextField('Hero 說明文字',
                                        default='透過 AI Glasses 配套 APP，輕鬆完成設備配對、AI 設定與導航控制，讓您的智慧眼鏡發揮 100% 效能。')

    # 下載卡片
    app_name = models.CharField('APP 名稱', max_length=50, default='AI Glasses 配套 APP')
    app_version = models.CharField('APP 版本號', max_length=20, default='1.0.0')
    app_requirement = models.CharField('系統要求', max_length=50, default='Android 8.0 以上')
    apk_url = models.CharField('APK 下載連結', max_length=300, default='/media/downloads/aiglass.apk')
    btn_download = models.CharField('下載按鈕文字', max_length=30, default='下載 Android APK')
    badge_1 = models.CharField('徽章 1', max_length=20, default='安全驗證')
    badge_2 = models.CharField('徽章 2', max_length=20, default='免費下載')
    badge_3 = models.CharField('徽章 3', max_length=20, default='無廣告')
    hardware_note = models.CharField('硬體搭配提示', max_length=100, default='需搭配 AI 導航智慧眼鏡硬體使用。')
    hardware_link_text = models.CharField('購買硬體連結文字', max_length=20, default='購買硬體')
    ios_note = models.CharField('iOS 版本說明', max_length=100, default='iOS 版本開發中，敬請期待。')

    # 功能特色區塊
    features_title = models.CharField('功能特色區塊標題', max_length=100, default='APP 核心功能')
    features_subtitle = models.TextField('功能特色區塊副標題',
                                         default='從設備配對到 AI 設定，一支 APP 完整管理您的智慧眼鏡。')

    # 安裝步驟區塊
    steps_title = models.CharField('安裝步驟區塊標題', max_length=100, default='四步驟快速上手')
    steps_subtitle = models.TextField('安裝步驟區塊副標題', default='從下載到開始使用，只需幾分鐘。')

    # CTA
    cta_title = models.CharField('CTA 標題', max_length=100, default='還沒有智慧眼鏡？')
    cta_description = models.TextField('CTA 說明文字',
                                       default='先購買硬體，再下載 APP，即可開始體驗 AI 穿戴未來。')
    cta_btn_buy = models.CharField('CTA 購買按鈕', max_length=30, default='立即購買眼鏡')
    cta_btn_specs = models.CharField('CTA 規格按鈕', max_length=30, default='查看產品規格')

    class Meta:
        verbose_name = 'APP 下載頁'
        verbose_name_plural = 'APP 下載頁'

    def __str__(self):
        return 'APP 下載頁內容'


class DownloadFeature(models.Model):
    """APP 下載頁：功能特色項目"""
    icon_svg = models.TextField('圖示 SVG path',
                                help_text='SVG 的 path d 屬性值（不含外層標籤）',
                                default='')
    title = models.CharField('標題', max_length=50)
    description = models.TextField('說明')
    order = models.PositiveIntegerField('排序', default=0)

    class Meta:
        ordering = ['order']
        verbose_name = 'APP 功能特色'
        verbose_name_plural = 'APP 功能特色'

    def __str__(self):
        return self.title


class DownloadStep(models.Model):
    """APP 下載頁：安裝步驟"""
    step_number = models.CharField('步驟編號', max_length=10, help_text='例如：01、02')
    title = models.CharField('標題', max_length=50)
    description = models.TextField('說明')
    order = models.PositiveIntegerField('排序', default=0)

    class Meta:
        ordering = ['order']
        verbose_name = '安裝步驟'
        verbose_name_plural = '安裝步驟'

    def __str__(self):
        return f'{self.step_number} - {self.title}'


# ── 購買頁 ───────────────────────────────────────────────────────

class PurchasePageContent(SingletonModel):
    """購買頁所有可編輯內容"""

    page_title = models.CharField('頁面標題', max_length=50, default='立即購買')
    subtitle = models.TextField('頁面副標題',
                                default='填寫以下資訊完成訂購，我們將在 1-2 個工作天內聯繫您確認出貨細節。')
    order_summary_title = models.CharField('訂單摘要標題', max_length=30, default='訂單摘要')
    product_emoji = models.CharField('商品圖示', max_length=10, default='\U0001f97d',
                                     help_text='商品列表中的 Emoji 圖示')
    label_quantity = models.CharField('數量標籤', max_length=20, default='數量')
    label_unit_price = models.CharField('單價標籤', max_length=20, default='單價')
    label_discount = models.CharField('優惠折扣標籤', max_length=20, default='優惠折扣')
    label_total = models.CharField('總計標籤', max_length=20, default='總計')
    label_name = models.CharField('姓名欄位標籤', max_length=20, default='姓名')
    label_email = models.CharField('Email 欄位標籤', max_length=20, default='Email')
    label_phone = models.CharField('電話欄位標籤', max_length=20, default='電話')
    label_address = models.CharField('收件地址標籤', max_length=30, default='收件地址')
    label_notes = models.CharField('備註標籤', max_length=30, default='備註（選填）')
    placeholder_name = models.CharField('姓名預設文字', max_length=50, default='請輸入您的姓名')
    placeholder_email = models.CharField('Email 預設文字', max_length=50, default='example@mail.com')
    placeholder_phone = models.CharField('電話預設文字', max_length=50, default='09XX-XXX-XXX')
    placeholder_address = models.TextField('地址預設文字', default='請輸入完整收件地址（含縣市、鄉鎮、路名、門牌號碼）')
    placeholder_notes = models.CharField('備註預設文字', max_length=100, default='有任何特殊需求請填寫於此')
    btn_submit = models.CharField('提交按鈕文字', max_length=30, default='確認訂購',
                                  help_text='金額會自動帶入')
    btn_submitting = models.CharField('提交中按鈕文字', max_length=30, default='處理中...')

    # 成功頁面
    success_icon = models.CharField('成功圖示', max_length=10, default='\u2705')
    success_title = models.CharField('成功標題', max_length=50, default='訂單建立成功！')
    success_label_order = models.CharField('訂單編號標籤', max_length=20, default='訂單編號')
    success_label_buyer = models.CharField('購買人標籤', max_length=20, default='購買人')
    success_label_amount = models.CharField('總金額標籤', max_length=20, default='總金額')
    success_email_hint = models.TextField('成功後 Email 提示',
                                          default='確認信將寄至 {email}，我們將儘快與您聯繫。',
                                          help_text='{email} 會替換為實際的 Email 地址')
    btn_reorder = models.CharField('再次訂購按鈕', max_length=20, default='再次訂購')

    class Meta:
        verbose_name = '購買頁'
        verbose_name_plural = '購買頁'

    def __str__(self):
        return '購買頁內容'


# ── 團隊頁 ───────────────────────────────────────────────────────

class AppServerConfig(SingletonModel):
    """APP 伺服器連線設定（後台管理員設定，APP 啟動時讀取）"""
    server_url = models.CharField(
        'AI 伺服器 URL', max_length=500, blank=True, default='',
        help_text='APP 連線的 AI 伺服器位址，例如：https://xxxx.devtunnels.ms 或 http://192.168.1.100:8081',
    )
    support_phone = models.CharField(
        '客服電話', max_length=30, blank=True, default='',
        help_text='視障使用者連線失敗時顯示的客服電話號碼，例如：0800-123-456',
    )
    note = models.TextField(
        '備註', blank=True, default='',
        help_text='說明目前伺服器狀態，例如：DevTunnel URL，每次重啟需更新',
    )
    updated_at = models.DateTimeField('最後更新', auto_now=True)

    class Meta:
        verbose_name = 'APP 伺服器設定'
        verbose_name_plural = 'APP 伺服器設定'

    def __str__(self):
        return 'APP 伺服器設定'


class AnnouncementTag(models.Model):
    """公告標籤（支援前台篩選）"""
    name = models.CharField('標籤名稱', max_length=50, unique=True)
    slug = models.SlugField('URL Slug', max_length=50, unique=True)
    color = models.CharField('顏色', max_length=20, default='#6366f1',
                             help_text='標籤顯示顏色（Hex 色碼）')
    created_at = models.DateTimeField('建立時間', auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = '公告標籤'
        verbose_name_plural = '公告標籤'

    def __str__(self):
        return self.name


class AppAnnouncement(models.Model):
    """管理員發送給 APP 視障使用者的公告（版本更新、維護、新功能等）"""
    TYPE_CHOICES = [
        ('version_update', '版本更新'),
        ('maintenance',    '系統維護'),
        ('new_feature',    '新功能'),
        ('general',        '一般通知'),
    ]

    title        = models.CharField('標題', max_length=100)
    body         = models.TextField('內容')
    type         = models.CharField('類型', max_length=20,
                                    choices=TYPE_CHOICES, default='general')
    is_active    = models.BooleanField('啟用', default=True)
    scheduled_at = models.DateTimeField(
        '排程時間', null=True, blank=True,
        help_text='留空表示立即生效；設定後到達該時間才對 APP 可見',
    )
    # 標籤系統與網站顯示
    tags = models.ManyToManyField(
        AnnouncementTag,
        verbose_name='標籤',
        blank=True,
        related_name='announcements'
    )
    show_on_website = models.BooleanField(
        '顯示於網站',
        default=False,
        help_text='勾選後，前台公告頁會顯示此公告'
    )
    created_at   = models.DateTimeField('建立時間', auto_now_add=True)
    updated_at   = models.DateTimeField('更新時間', auto_now=True)

    class Meta:
        ordering        = ['-created_at']
        verbose_name    = 'APP 公告'
        verbose_name_plural = 'APP 公告列表'

    def __str__(self):
        return f'[{self.get_type_display()}] {self.title}'


class ImpactFeedback(models.Model):
    """APP 摔倒偵測回饋記錄，用於調整撞擊偵測靈敏度"""
    magnitude        = models.FloatField('加速度合力 (m/s²)')
    outcome          = models.CharField('結果', max_length=20,
                                        help_text='auto_dialed / cancelled')
    is_false_positive = models.BooleanField('是否誤判', default=False)
    note             = models.TextField('備註', blank=True, default='')
    created_at       = models.DateTimeField('記錄時間', auto_now_add=True)

    class Meta:
        ordering        = ['-created_at']
        verbose_name    = '撞擊回饋'
        verbose_name_plural = '撞擊回饋記錄'

    def __str__(self):
        label = '誤判' if self.is_false_positive else '真實'
        return f'{self.created_at:%Y-%m-%d %H:%M} | {self.magnitude:.1f} m/s² | {label}'


class TeamPageContent(SingletonModel):
    """團隊頁所有可編輯內容"""

    page_title = models.CharField('頁面標題', max_length=50, default='關於團隊')
    subtitle = models.TextField('頁面副標題',
                                default='本專案結合開源社群的創意與我們開發團隊的技術，共同打造 AI 智慧眼鏡的未來。')
    reference_title = models.CharField('原專案參考者區塊標題', max_length=50, default='原專案參考者')
    reference_description = models.TextField('原專案參考者說明',
                                             default='感謝以下開源貢獻者的創作，本專案基於')
    reference_link_text = models.CharField('原專案連結文字', max_length=50, default='OpenAIglasses_for_Navigation')
    reference_link_url = models.URLField('原專案連結 URL', max_length=300,
                                         default='https://github.com/AI-FanGe/OpenAIglasses_for_Navigation')
    developer_title = models.CharField('開發團隊區塊標題', max_length=50, default='我們的開發團隊')
    empty_message = models.TextField('無成員提示',
                                     default='團隊成員資料載入中，或請至後台管理介面新增成員。')

    class Meta:
        verbose_name = '團隊頁'
        verbose_name_plural = '團隊頁'

    def __str__(self):
        return '團隊頁內容'
