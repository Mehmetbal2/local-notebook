"""Server-side messages in the user's interface language.

The frontend sends the selected UI language in the `X-UI-Language` header; a
middleware stores it for the duration of the request. Background tasks receive
the language they were started with and call `set_language` themselves.

Only text a person reads goes through here (API errors, connection-test results,
file-processing status, generation errors). Log lines and prompts sent to models
stay as they are.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional

SUPPORTED = ("tr", "en", "zh")
DEFAULT_LANGUAGE = "en"

_language: ContextVar[str] = ContextVar("ui_language", default=DEFAULT_LANGUAGE)


def normalize_language(value: Optional[str]) -> str:
    """'tr', 'tr-TR', 'Turkish', 'Türkçe', 'zh-CN', 'Chinese', 'en-US', an Accept-Language header... -> 'tr' | 'en' | 'zh'."""
    raw = (value or "").strip().lower()
    if not raw:
        return DEFAULT_LANGUAGE
    first = raw.split(",")[0].split(";")[0].strip().replace("_", "-")
    if first.startswith(("tr", "türk", "turk")):
        return "tr"
    if first.startswith(("zh", "chinese", "中文", "简体")):
        return "zh"
    return "en"


def set_language(value: Optional[str]) -> Token:
    return _language.set(normalize_language(value))


def reset_language(token: Token) -> None:
    _language.reset(token)


def current_language() -> str:
    return _language.get()


def msg(key: str, **params) -> str:
    """The message `key` in the current language, with `{name}` placeholders filled in."""
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    text = entry.get(current_language()) or entry["en"]
    return text.format(**params) if params else text


# key: {tr, en, zh}
MESSAGES: dict[str, dict[str, str]] = {
    # ---- connection tests (Settings) ----
    "conn_ok": {"tr": "Bağlantı başarılı", "en": "Connection successful", "zh": "连接成功"},
    "conn_ok_model": {"tr": "Bağlantı başarılı · {model}", "en": "Connection successful · {model}", "zh": "连接成功 · {model}"},
    "conn_ok_embedding": {
        "tr": "Bağlantı başarılı · {model} · boyut {dim}",
        "en": "Connection successful · {model} · dimension {dim}",
        "zh": "连接成功 · {model} · 维度 {dim}",
    },
    "service_returned": {"tr": "Servis {status} yanıtı döndürdü", "en": "The service returned {status}", "zh": "服务返回 {status}"},
    "cannot_connect": {"tr": "Servis adresine bağlanılamadı", "en": "Could not reach the service address", "zh": "无法连接到服务地址"},
    "cannot_connect_url": {"tr": "{url} adresine bağlanılamadı", "en": "Could not connect to {url}", "zh": "无法连接到 {url}"},
    "conn_timeout_url": {"tr": "Bağlantı zaman aşımına uğradı ({url})", "en": "Connection timed out ({url})", "zh": "连接超时 ({url})"},
    "missing_api_key": {"tr": "API anahtarı girilmemiş", "en": "The API key is not set", "zh": "未配置 API Key"},
    "missing_base_url": {"tr": "Base URL girilmemiş", "en": "The base URL is not set", "zh": "未配置 Base URL"},
    "missing_model": {"tr": "Model adı girilmemiş", "en": "The model name is not set", "zh": "未配置模型名称"},
    "missing_service_url": {"tr": "Servis adresi girilmemiş", "en": "The service address is not set", "zh": "未配置服务地址"},
    "searxng_ok": {"tr": "SearXNG çalışıyor: {count} sonuç ({engines})", "en": "SearXNG is working: {count} results ({engines})", "zh": "SearXNG 正常：{count} 条结果（{engines}）"},
    "searxng_cannot_connect": {"tr": "SearXNG'ye bağlanılamadı ({url}). OrbStack/Docker açık mı? Ardından ./start.sh restart çalıştırın.", "en": "Could not connect to SearXNG ({url}). Is OrbStack/Docker running? Then run ./start.sh restart.", "zh": "无法连接 SearXNG（{url}）。OrbStack/Docker 是否在运行？然后执行 ./start.sh restart。"},
    "searxng_json_disabled": {"tr": "SearXNG JSON çıktısını reddetti; settings.yml içinde search.formats altına json ekleyin.", "en": "SearXNG refused JSON output; add json under search.formats in settings.yml.", "zh": "SearXNG 拒绝 JSON 输出；请在 settings.yml 的 search.formats 中加入 json。"},
    "searxng_rate_limited": {"tr": "SearXNG istek sınırına takıldı; biraz sonra tekrar deneyin.", "en": "SearXNG rate limit reached; try again shortly.", "zh": "SearXNG 请求过多，请稍后重试。"},
    "searxng_no_results": {"tr": "SearXNG yanıt verdi ama sonuç döndürmedi; arama motorları engellenmiş olabilir.", "en": "SearXNG answered but returned no results; the search engines may be blocked.", "zh": "SearXNG 有响应但没有结果，搜索引擎可能被屏蔽。"},
    "websource_label_url": {"tr": "Kaynak", "en": "Source", "zh": "来源"},
    "websource_label_authors": {"tr": "Yazar(lar)", "en": "Author(s)", "zh": "作者"},
    "websource_label_published": {"tr": "Yayın tarihi", "en": "Published", "zh": "发布日期"},
    "websource_label_site": {"tr": "Yayıncı/Site", "en": "Publisher/Site", "zh": "出版方/网站"},
    "websource_label_accessed": {"tr": "Erişim tarihi", "en": "Accessed", "zh": "访问日期"},
    "websource_nothing_selected": {"tr": "İçe aktarılacak bağlantı seçilmedi", "en": "No links selected to import", "zh": "未选择要导入的链接"},
    "websource_no_text": {"tr": "Sayfada okunabilir metin bulunamadı (giriş gerektiriyor veya JavaScript ile yükleniyor olabilir)", "en": "No readable text on the page (it may need a login or load with JavaScript)", "zh": "页面没有可读文本（可能需要登录或由 JavaScript 加载）"},
    "websource_too_large": {"tr": "Dosya çok büyük", "en": "The file is too large", "zh": "文件过大"},
    "websource_unsupported": {"tr": "Desteklenmeyen içerik türü", "en": "Unsupported content type", "zh": "不支持的内容类型"},
    "websource_http_error": {"tr": "Site hata döndürdü (HTTP {status})", "en": "The site returned an error (HTTP {status})", "zh": "网站返回错误（HTTP {status}）"},
    "websource_timeout": {"tr": "Site zamanında yanıt vermedi", "en": "The site did not respond in time", "zh": "网站响应超时"},
    "invalid_service_url": {"tr": "Geçersiz servis adresi. http:// ya da https:// ile başlayan bir adres girin.", "en": "Invalid service address. Enter an address starting with http:// or https://.", "zh": "服务地址无效，请输入以 http:// 或 https:// 开头的地址。"},
    "invalid_service_url_credentials": {"tr": "Adrese kullanıcı adı veya şifre yazmayın; API anahtarını kendi alanına girin.", "en": "Do not put a user name or password in the address; enter the API key in its own field.", "zh": "请勿在地址中包含用户名或密码，请在单独的字段中填写 API 密钥。"},
    "websource_blocked": {"tr": "Bu adres genel internette değil (yerel ağ ya da sunucunun kendisi); güvenlik nedeniyle indirilmedi.", "en": "This address is not on the public internet (a local network or the server itself), so it was not downloaded for safety.", "zh": "该地址不在公共互联网上（本地网络或服务器本身），出于安全考虑未下载。"},
    "websource_fetch_failed": {"tr": "Sayfa indirilemedi", "en": "The page could not be downloaded", "zh": "无法下载页面"},
    "research_queued": {"tr": "Sırada bekliyor…", "en": "Queued…", "zh": "排队中…"},
    "research_planning": {"tr": "Konu alt sorulara bölünüyor…", "en": "Breaking the topic into sub-questions…", "zh": "正在拆分子问题…"},
    "research_searching": {"tr": "{count} alt soru için kaynak aranıyor ve okunuyor…", "en": "Searching and reading sources for {count} sub-questions…", "zh": "正在为 {count} 个子问题搜索并阅读来源…"},
    "research_read": {"tr": "{count} kaynak okundu", "en": "{count} sources read", "zh": "已阅读 {count} 个来源"},
    "research_gaps": {"tr": "{count} kaynak okundu; eksik kalan konular için ek arama yapılıyor…", "en": "{count} sources read; searching again for gaps…", "zh": "已阅读 {count} 个来源；正在补充搜索…"},
    "research_writing": {"tr": "{count} kaynaktan atıflı rapor yazılıyor (birkaç dakika sürebilir)…", "en": "Writing the cited report from {count} sources (may take a few minutes)…", "zh": "正在根据 {count} 个来源撰写带引用的报告（可能需要几分钟）…"},
    "research_no_sources": {"tr": "Okunabilir kaynak bulunamadı; konuyu farklı kelimelerle deneyin.", "en": "No readable sources were found; try other words.", "zh": "未找到可读来源，请换个说法。"},
    "research_report_failed": {"tr": "Model raporu yazamadı (sunucu zamanında yanıt vermedi). Okunan kaynaklar saklandı; \"Yeniden oluştur\" raporu aramayı tekrarlamadan yeniden yazar.", "en": "The model could not write the report (the server did not answer in time). The sources read are kept; \"Regenerate\" writes the report again without searching.", "zh": "模型未能撰写报告（服务器未及时响应）。已保存所读来源；“重新生成”将直接重写报告，无需重新搜索。"},
    "research_restarted": {"tr": "Uygulama yeniden başladığı için araştırma baştan başlatıldı…", "en": "Restarted from the beginning after the app restarted…", "zh": "应用重启，研究已重新开始…"},
    "websource_abstract_only_note": {"tr": "Bu çalışmanın ücretsiz tam metni bulunamadı; yalnızca yayıncı sayfasındaki bilgiler (özet) alındı.", "en": "No free full text of this work was found; only the publisher page (abstract) was saved.", "zh": "未找到该文献的免费全文，仅保存了出版方页面（摘要）。"},
    "preflight_llm": {"tr": "LLM (dil modeli)", "en": "LLM (language model)", "zh": "LLM 大语言模型"},
    "preflight_embedding": {"tr": "Gömme (embedding) modeli", "en": "Embedding model", "zh": "Embedding 向量模型"},
    "embedding_switch_blocked": {
        "tr": "Şu anda {count} ayrıştırılmış belge var. Gömme servisini değiştirdiğinizde eski vektör tablosu sıfırlanır; sonrasında \"Belgeleri Yeniden Vektörleştir\" düğmesiyle mevcut özetleri koruyarak tüm belgeleri yeniden vektörleştirebilirsiniz.",
        "en": "There are {count} parsed documents. Switching the embedding service resets the old vector collection; afterwards you can click \"Re-index Documents\" to rebuild vectors while keeping existing summaries.",
        "zh": "当前有 {count} 个已解析的文档。切换 Embedding 服务后将重置旧向量集合，随后可点击「重新向量化文档」保留现有摘要重建所有向量。",
    },
    "embedding_active_files_blocked": {
        "tr": "Şu anda işlenmekte olan {count} belge var. Gömme modelini değiştirmeden veya yeniden vektörleştirme başlatmadan önce devam eden işlemlerin tamamlanmasını bekleyin ya da kaynaklar listesinden durdurun.",
        "en": "There are {count} document(s) currently being processed. Wait for active processing to finish or stop them from the sources list before switching the embedding model or re-indexing.",
        "zh": "当前有 {count} 个文档正在处理中。请等待处理完成或在来源列表中停止它们，然后再切换 Embedding 模型或重新向量化。",
    },
    "reindex_confirm_required": {
        "tr": "Yeniden vektörleştirme işlemi için onay gereklidir (confirm=true).",
        "en": "Confirmation is required to re-index documents (confirm=true).",
        "zh": "重新向量化操作需要确认（confirm=true）。",
    },
    "vector_reset_failed": {
        "tr": "Vektör koleksiyonu sıfırlanamadı ({error}). Ayarlar > Gömme > Belgeleri Yeniden Vektörleştir düğmesiyle tekrar deneyebilirsiniz.",
        "en": "Could not reset vector collections ({error}). You can retry from Settings > Embedding > Re-index Documents.",
        "zh": "无法重置向量集合（{error}）。可在「设置 → Embedding → 重新向量化文档」中重试。",
    },
    "embedding_dim_mismatch": {
        "tr": "Milvus vektör tablosunun boyutu ({existing_dim}) ile aktif gömme modelinin boyutu ({new_dim}) uyuşmuyor. Ayarlar > Gömme bölümünden model değişikliğini onaylayarak kaydedin veya mevcut belgeleri yeniden işleyin.",
        "en": "The Milvus vector collection dimension ({existing_dim}) does not match the active embedding model dimension ({new_dim}). Confirm and save the embedding model switch in Settings > Embedding, or reprocess your documents.",
        "zh": "Milvus 向量集合维度（{existing_dim}）与当前 Embedding 模型维度（{new_dim}）不一致。请在「设置 → Embedding」确认保存模型切换，或重新处理文档。",
    },
    "local_model_dir_missing": {
        "tr": "Yerel gömme modeli dizini bulunamadı: {path}",
        "en": "Local embedding model directory not found: {path}",
        "zh": "未找到本地 Embedding 模型目录：{path}",
    },
    # ---- file processing ----
    "processing_pdf": {"tr": "PDF ayrıştırılıyor...", "en": "Parsing PDF...", "zh": "正在解析 PDF..."},
    "processing_audio": {"tr": "Ses yazıya dökülüyor...", "en": "Transcribing audio...", "zh": "正在转写音频..."},
    "processing_image": {"tr": "Görsel analiz ediliyor...", "en": "Analyzing image...", "zh": "正在分析图片..."},
    "processing_text": {"tr": "İçerik okunuyor...", "en": "Reading content...", "zh": "正在读取内容..."},
    "reembedding_vectors": {"tr": "Vektörler yeniden oluşturuluyor...", "en": "Rebuilding vectors...", "zh": "正在重新生成向量..."},
    "reindex_queued": {
        "tr": "{count} belge için yeniden vektörleştirme başlatıldı (mevcut metin ve özetler korunur).",
        "en": "Re-indexing started for {count} document(s) (existing text and summaries are preserved).",
        "zh": "已为 {count} 个文档启动重新向量化（保留现有文本与摘要）。",
    },
    "embedding_url_missing": {
        "tr": "Gömme (embedding) servisi adresi yapılandırılmamış. Ayarlar'dan yapılandırıp dosyayı yeniden yükleyin.",
        "en": "The embedding service address is not set. Configure it in Settings and upload the file again.",
        "zh": "Embedding 服务地址未配置。请在「设置」页面配置后重新上传。",
    },
    "embedding_key_missing": {
        "tr": "Gömme (embedding) API anahtarı yapılandırılmamış. Ayarlar'dan girip dosyayı yeniden yükleyin.",
        "en": "The embedding API key is not set. Enter it in Settings and upload the file again.",
        "zh": "Embedding API Key 未配置。请在「设置」页面配置 Embedding API Key 后重新上传。",
    },
    "file_not_ready": {"tr": "Dosyanın işlenmesi henüz tamamlanmadı", "en": "The file has not finished processing", "zh": "文件尚未处理完成"},
    "unsupported_file_type": {"tr": "Desteklenmeyen dosya türü: {ext}", "en": "Unsupported file type: {ext}", "zh": "不支持的文件类型: {ext}"},
    "file_not_found": {"tr": "Dosya bulunamadı: {path}", "en": "File not found: {path}", "zh": "文件不存在: {path}"},
    "file_not_reprocessable": {
        "tr": "Şu anda işlenmekte olan dosyalar yeniden işlenemez; önce işlemi durdurun.",
        "en": "Files that are currently being processed cannot be reprocessed; stop them first.",
        "zh": "正在处理中的文件无法重新处理，请先停止处理。",
    },
    "queue_unavailable_file": {"tr": "Arka plan görev servisi kullanılamıyor; dosya işlenemiyor", "en": "The background task service is unavailable, so the file cannot be processed", "zh": "后台任务服务不可用，无法处理文件"},
    "unknown_error": {"tr": "Bilinmeyen hata", "en": "Unknown error", "zh": "未知错误"},
    # ---- speech to text ----
    "asr_not_configured": {
        "tr": "Ses yazıya dökme servisi yapılandırılmamış. Ayarlar > Ses bölümünde API anahtarı, Base URL ve model adını girip dosyayı yeniden yükleyin.",
        "en": "The speech-to-text service is not configured. Enter the API key, base URL and model name in Settings > Audio and upload the file again.",
        "zh": "语音转写服务未配置。请在「设置 → 语音」配置 API Key、Base URL 和模型名称后重新上传。",
    },
    "asr_not_configured_dictation": {"tr": "Sesle yazmak için Ayarlar > Ses bölümünde konuşma tanıma (ASR) servisini yapılandırın.", "en": "To dictate, configure the speech recognition (ASR) service in Settings > Audio.", "zh": "如需语音输入，请在「设置 → 语音」中配置语音识别（ASR）服务。"},
    "dictation_empty": {"tr": "Kayıt boş", "en": "The recording is empty", "zh": "录音为空"},
    "dictation_too_long": {"tr": "Kayıt çok uzun; daha kısa parçalar halinde konuşun", "en": "The recording is too long; speak in shorter parts", "zh": "录音过长，请分段说话"},
    "asr_failed": {"tr": "Ses tanıma başarısız", "en": "Speech recognition failed", "zh": "语音识别失败"},
    "asr_failed_detail": {"tr": "Ses tanıma başarısız: {error}", "en": "Speech recognition failed: {error}", "zh": "语音识别失败: {error}"},
    "asr_timeout": {"tr": "Ses yazıya dökme servisi zaman aşımına uğradı ({seconds} sn)", "en": "The speech-to-text service timed out ({seconds} s)", "zh": "语音转写服务超时（{seconds}秒）"},
    "asr_cannot_connect": {"tr": "Ses yazıya dökme servisine bağlanılamadı: {url}", "en": "Could not connect to the speech-to-text service: {url}", "zh": "无法连接语音转写服务: {url}"},
    "asr_non_json": {"tr": "Ses yazıya dökme servisi JSON olmayan bir yanıt döndürdü", "en": "The speech-to-text service returned a non-JSON response", "zh": "语音转写服务返回了非 JSON 响应"},
    "asr_bad_format": {"tr": "Ses yazıya dökme servisinin yanıtı beklenmeyen biçimde", "en": "The speech-to-text service response has an unexpected format", "zh": "语音转写服务响应格式不正确"},
    # ---- PDF / OCR ----
    "ocr_pages_failed": {"tr": "{start}-{end}. sayfalar ayrıştırılamadı: {error}", "en": "Pages {start}-{end} could not be parsed: {error}", "zh": "第 {start}-{end} 页解析失败: {error}"},
    "ocr_non_json": {"tr": "OCR servisi JSON olmayan bir yanıt döndürdü", "en": "The OCR service returned a non-JSON response", "zh": "PDF OCR 服务返回了非 JSON 对象响应"},
    "ocr_cannot_connect": {"tr": "OCR servisine bağlanılamadı: {url}", "en": "Could not connect to the OCR service: {url}", "zh": "无法连接 PDF OCR 服务: {url}"},
    "ocr_timeout": {"tr": "OCR servisi zaman aşımına uğradı ({seconds} sn)", "en": "The OCR service timed out ({seconds} s)", "zh": "PDF OCR 服务超时（{seconds}秒）"},
    "ocr_failed": {"tr": "PDF ayrıştırılamadı: {error}", "en": "The PDF could not be parsed: {error}", "zh": "PDF 解析失败: {error}"},
    "ocr_not_configured": {
        "tr": "OCR servisi yapılandırılmamış. Ayarlar > PDF ayrıştırma bölümünde API anahtarı, Base URL ve model adını girin ya da Yerel veya Otomatik motoru seçin.",
        "en": "The OCR service is not configured. Enter the API key, base URL and model name in Settings > PDF parsing, or choose the Local or Automatic engine.",
        "zh": "OCR 服务未配置。请在「设置 → PDF 解析」中填写 API Key、Base URL 和模型名称，或选择本地或自动引擎。",
    },
    "ocr_parse_failed": {"tr": "OCR servisi PDF'i ayrıştıramadı: {error}", "en": "The OCR service could not parse the PDF: {error}", "zh": "OCR 服务无法解析该 PDF: {error}"},
    "pdf_no_text": {
        "tr": "Bu PDF'ten metin çıkarılamadı (muhtemelen taranmış). Ayarlar > PDF ayrıştırma bölümünden bir OCR servisi yapılandırın.",
        "en": "No text could be extracted from this PDF (it is probably scanned). Configure an OCR service in Settings > PDF parsing.",
        "zh": "无法从此 PDF 中提取文本（可能是扫描件）。请在「设置 → PDF 解析」中配置 OCR 服务。",
    },
    "pymupdf_missing": {
        "tr": "Yerel PDF ayrıştırma için PyMuPDF kurulu değil. Sanal ortamda `pip install pymupdf` çalıştırın veya Ayarlar > PDF ayrıştırma bölümünden OCR servisini seçin.",
        "en": "PyMuPDF is not installed for local PDF parsing. Run `pip install pymupdf` in the virtual environment, or choose the OCR service in Settings > PDF parsing.",
        "zh": "本地 PDF 解析需要 PyMuPDF。请在虚拟环境中运行 `pip install pymupdf`，或在「设置 → PDF 解析」中选择 OCR 服务。",
    },
    # ---- PDF size limits ----
    "parser_memory_limit": {"tr": "Belge işlenirken bellek sınırı ({limit} MB) aşıldı; dosya açıldığında aşırı büyüyor olabilir. Güvenlik nedeniyle işlem durduruldu.", "en": "Processing the document went over the memory limit ({limit} MB); the file may expand to an unreasonable size. It was stopped for safety.", "zh": "处理该文档时超出内存上限（{limit} MB），文件展开后可能过大，出于安全考虑已停止。"},
    "image_too_large": {"tr": "Görsel çok büyük ({size} MB; sınır {limit} MB), görsel modeline gönderilmedi.", "en": "The image is too large ({size} MB; limit {limit} MB) and was not sent to the vision model.", "zh": "图片过大（{size} MB；上限 {limit} MB），未发送给视觉模型。"},
    "parser_failed": {"tr": "Belge işleme süreci beklenmedik biçimde sonlandı (kod {code}).", "en": "The document processing step ended unexpectedly (code {code}).", "zh": "文档处理进程意外结束（代码 {code}）。"},
    "parser_time_limit": {"tr": "Belge işleme süre sınırını ({limit} dk) aştı ve durduruldu.", "en": "Processing the document took longer than the time limit ({limit} min) and was stopped.", "zh": "处理该文档超过时间上限（{limit} 分钟），已停止。"},
    "pdf_too_many_pages": {"tr": "PDF çok fazla sayfa içeriyor ({count} sayfa; sınır {limit}). Güvenlik nedeniyle işlenmedi.", "en": "The PDF has too many pages ({count} pages; limit {limit}). It was not processed for safety.", "zh": "该 PDF 页数过多（{count} 页；上限 {limit}），出于安全考虑未处理。"},
    "pdf_too_large": {"tr": "PDF açıldığında çok büyük bir içeriğe dönüşüyor (sınır {limit} MB). Güvenlik nedeniyle işlenmedi.", "en": "The PDF expands to an unreasonable amount of content when opened (limit {limit} MB). It was not processed for safety.", "zh": "该 PDF 展开后内容过大（上限 {limit} MB），出于安全考虑未处理。"},
    # ---- EPUB ----
    "archive_too_large": {"tr": "Belge açıldığında çok büyük bir boyuta ulaşıyor ({size} MB, {count} parça; sınır {limit} MB). Güvenlik nedeniyle işlenmedi.", "en": "The document expands to an unreasonable size when unpacked ({size} MB, {count} parts; limit {limit} MB). It was not processed for safety.", "zh": "该文档解压后体积过大（{size} MB，{count} 个部分；上限 {limit} MB），出于安全考虑未处理。"},
    "epub_corrupt": {"tr": "EPUB ayrıştırılamadı; dosya bozuk ya da biçimi standart dışı olabilir: {error}", "en": "The EPUB could not be parsed; the file may be damaged or malformed: {error}", "zh": "EPUB 解析失败,文件可能损坏或格式不规范: {error}"},
    "epub_no_text": {
        "tr": "EPUB'dan metin çıkarılamadı. Dosya şifreli (DRM), sabit düzenli ya da görsel tabanlı olabilir; bu türler henüz desteklenmiyor.",
        "en": "No text could be extracted from the EPUB. It may be encrypted (DRM), fixed-layout or image-based; these are not supported yet.",
        "zh": "未能从 EPUB 中提取到正文文本。该文件可能是加密(DRM)、固定版式或图片型 EPUB,暂不支持。",
    },
    # ---- quick tools & reports ----
    "feature_type_missing": {"tr": "Hızlı araç türü eksik", "en": "The quick tool type is missing", "zh": "缺少快捷工具类型"},
    "select_at_least_one_file": {"tr": "En az bir dosya seçin", "en": "Select at least one file", "zh": "请选择至少一个文件"},
    "queue_unavailable_feature": {"tr": "Arka plan görev servisi kullanılamıyor; hızlı araç üretilemiyor", "en": "The background task service is unavailable, so the quick tool cannot be generated", "zh": "后台任务服务不可用，无法生成快捷工具内容"},
    "queue_unavailable_report": {"tr": "Arka plan görev servisi kullanılamıyor; rapor üretilemiyor", "en": "The background task service is unavailable, so the report cannot be generated", "zh": "后台任务服务不可用，无法生成报告"},
    "workflow_prompt_missing": {"tr": "Rapor gereksinimlerini girin", "en": "Enter the report requirements", "zh": "请输入工作流要求"},
    "workflow_type_missing": {"tr": "Rapor türü eksik", "en": "The report type is missing", "zh": "缺少工作流类型"},
    "output_language_missing": {"tr": "Çıktı dili eksik", "en": "The output language is missing", "zh": "缺少输出语言"},
    "workflow_default_name": {"tr": "Rapor", "en": "Report", "zh": "工作流"},
    "workflow_cancelled": {"tr": "Kullanıcı tarafından durduruldu", "en": "Stopped by the user", "zh": "用户已停止生成"},
    "planning_failed": {"tr": "Planlama başarısız: {error}", "en": "Planning failed: {error}", "zh": "规划失败: {error}"},
    "section_timeout": {"tr": "Bölüm üretimi zaman aşımına uğradı ({seconds} sn)", "en": "Section generation timed out ({seconds} s)", "zh": "栏目生成超时（{seconds} 秒）"},
    "llm_not_configured": {"tr": "LLM yapılandırılmamış", "en": "The LLM is not configured", "zh": "LLM 未配置"},
    "section_empty": {"tr": "Üretilen bölüm boş", "en": "The generated section is empty", "zh": "栏目生成结果为空"},
    "llm_step_timeout": {"tr": "LLM çağrısı zaman aşımına uğradı ({seconds} sn)", "en": "The LLM call timed out ({seconds} s)", "zh": "LLM 单轮调用超时（{seconds} 秒）"},
    "llm_call_failed": {"tr": "LLM çağrısı başarısız: {error}", "en": "The LLM call failed: {error}", "zh": "LLM 调用失败: {error}"},
    "report_title_llm_missing": {"tr": "LLM yapılandırılmadığı için rapor başlığı üretilemedi", "en": "The LLM is not configured, so the report title cannot be generated", "zh": "LLM 未配置，无法生成报告标题"},
    "report_title_prompt_missing": {"tr": "Rapor gereksinimleri eksik olduğu için başlık üretilemedi", "en": "The report requirements are missing, so the title cannot be generated", "zh": "缺少工作流要求，无法生成报告标题"},
    "report_title_language_missing": {"tr": "Çıktı dili eksik olduğu için başlık üretilemedi", "en": "The output language is missing, so the title cannot be generated", "zh": "缺少输出语言，无法生成报告标题"},
    "report_title_empty": {"tr": "Rapor başlığı üretilemedi ({attempts} deneme): model boş başlık döndürdü", "en": "The report title could not be generated after {attempts} attempts: the model returned an empty title", "zh": "报告标题生成失败，已尝试 {attempts} 次: 模型返回空标题"},
    "plan_llm_missing": {"tr": "LLM yapılandırılmadığı için rapor planlanamadı", "en": "The LLM is not configured, so the report cannot be planned", "zh": "LLM 未配置，无法规划报告"},
    "plan_prompt_missing": {"tr": "Rapor gereksinimleri eksik olduğu için planlama yapılamadı", "en": "The report requirements are missing, so the report cannot be planned", "zh": "缺少工作流要求，无法规划报告"},
    "plan_language_missing": {"tr": "Çıktı dili eksik olduğu için planlama yapılamadı", "en": "The output language is missing, so the report cannot be planned", "zh": "缺少输出语言，无法规划报告"},
    "plan_title_missing": {"tr": "Rapor başlığı eksik olduğu için planlama yapılamadı", "en": "The report title is missing, so the report cannot be planned", "zh": "缺少报告标题，无法规划报告"},
    "plan_structure_failed": {"tr": "Rapor yapısı planlanamadı ({attempts} deneme): {error}", "en": "The report structure could not be planned after {attempts} attempts: {error}", "zh": "规划结构失败，已尝试 {attempts} 次: {error}"},
    "plan_dependency_failed": {"tr": "Bölüm bağımlılıkları planlanamadı ({attempts} deneme): {error}", "en": "The section dependencies could not be planned after {attempts} attempts: {error}", "zh": "规划依赖失败，已尝试 {attempts} 次: {error}"},
    "plan_validation_failed": {"tr": "Plan son doğrulamayı geçemedi ({attempts} deneme): {error}", "en": "The plan failed final validation after {attempts} attempts: {error}", "zh": "规划最终校验失败，已尝试 {attempts} 次: {error}"},
    "plan_no_json_keys": {"tr": "Plan sonucunda {keys} içeren eksiksiz bir JSON nesnesi bulunamadı", "en": "No complete JSON object containing {keys} was found in the plan", "zh": "规划结果中未找到包含 {keys} 的完整 JSON object"},
    "plan_no_json": {"tr": "Plan sonucunda JSON nesnesi bulunamadı", "en": "No JSON object was found in the plan", "zh": "规划结果中未找到 JSON object"},
    # ---- text to speech ----
    "tts_not_configured": {
        "tr": "Sesli genel bakış ve podcast için Ayarlar > Ses bölümünde TTS (metinden sese) API anahtarını, Base URL'yi ve model adını yapılandırın.",
        "en": "To create audio overviews and podcasts, configure the TTS (text-to-speech) API key, base URL and model name in Settings > Audio.",
        "zh": "如需生成音频概览和播客，请在「设置 → 语音」中配置 TTS（文本转语音）API Key、Base URL 和模型名称。",
    },
    "podcast_not_dialogue": {"tr": "Podcast metni iki konuşmacılı diyalog biçiminde üretilemedi", "en": "The podcast script could not be produced as a two-speaker dialogue", "zh": "播客脚本未能生成为双人对话格式"},
    "tts_no_narration": {"tr": "Seslendirilecek metin üretilemedi", "en": "No text to narrate could be produced", "zh": "未能生成可朗读的文本"},
    "tts_no_text": {"tr": "Seslendirilecek metin bulunamadı", "en": "There is no text to read aloud", "zh": "没有可朗读的文本"},
    "tts_no_dialogue": {"tr": "Seslendirilecek konuşma bulunamadı", "en": "There is no dialogue to read aloud", "zh": "没有可朗读的对话"},
    "tts_empty_response": {"tr": "Ses üretilemedi (boş yanıt)", "en": "No audio was produced (empty response)", "zh": "未能生成音频（空响应）"},
    "tts_chunk_error": {"tr": "TTS hatası ({where}parça {index}/{total}): {error}", "en": "TTS error ({where}part {index}/{total}): {error}", "zh": "TTS 错误（{where}第 {index}/{total} 段）: {error}"},
    "tts_missing_url": {"tr": "TTS Base URL eksik", "en": "The TTS base URL is missing", "zh": "缺少 TTS Base URL"},
    "tts_missing_key": {"tr": "TTS API anahtarı eksik", "en": "The TTS API key is missing", "zh": "缺少 TTS API Key"},
    "tts_missing_model": {"tr": "TTS model adı eksik", "en": "The TTS model name is missing", "zh": "缺少 TTS 模型名称"},
    "tts_ready": {"tr": "TTS servisi hazır ({model} · {voice})", "en": "The TTS service is ready ({model} · {voice})", "zh": "TTS 服务已就绪（{model} · {voice}）"},
    "tts_cannot_connect": {"tr": "TTS servisine bağlanılamadı: {url}", "en": "Could not connect to the TTS service: {url}", "zh": "无法连接 TTS 服务: {url}"},
    "tts_timeout": {"tr": "TTS servisi zaman aşımına uğradı: {url}", "en": "The TTS service timed out: {url}", "zh": "TTS 服务超时: {url}"},
    "tts_check_failed": {"tr": "TTS kontrolü başarısız: {error}", "en": "The TTS check failed: {error}", "zh": "TTS 检查失败: {error}"},
    # ---- chat ----
    "chat_llm_key_missing": {"tr": "LLM API anahtarı yapılandırılmamış. Ayarlar > Model ayarları bölümünden girin.", "en": "The LLM API key is not set. Enter it in Settings > Model settings.", "zh": "LLM API key 未配置，请前往「设置 → LLM」填写。"},
    "chat_llm_model_missing": {"tr": "LLM modeli yapılandırılmamış. Ayarlar > Model ayarları bölümünden girin.", "en": "The LLM model is not set. Enter it in Settings > Model settings.", "zh": "LLM 模型未配置，请前往「设置 → LLM」填写。"},
    "chat_step_limit": {"tr": "Soru karmaşık olduğu için işlem adımı sınırına ulaşıldı. Soruyu sadeleştirmeyi deneyin.", "en": "The question was complex enough to reach the processing step limit. Try simplifying it.", "zh": "问题较为复杂，已达到处理步骤上限。请尝试简化提问。"},
    # ---- safe error messages (utils/errors.py) ----
    "err_timeout": {"tr": "Model servisi zamanında yanıt vermedi. Biraz sonra tekrar deneyin.", "en": "The model service did not respond in time. Try again shortly.", "zh": "模型服务未及时响应，请稍后重试。"},
    "err_connect": {"tr": "Model servisine bağlanılamadı. Adresi ve servisin çalıştığını kontrol edin.", "en": "Could not reach the model service. Check its address and that it is running.", "zh": "无法连接到模型服务，请检查地址以及服务是否在运行。"},
    "err_auth": {"tr": "Model servisi isteği reddetti: API anahtarı geçersiz ya da yetkisiz.", "en": "The model service rejected the request: the API key is invalid or not authorised.", "zh": "模型服务拒绝了请求：API 密钥无效或无权限。"},
    "err_rate_limit": {"tr": "Model servisinin istek ya da kota sınırına ulaşıldı. Biraz bekleyip tekrar deneyin.", "en": "The model service's rate or quota limit was reached. Wait a moment and try again.", "zh": "已达到模型服务的速率或配额限制，请稍候再试。"},
    "err_context": {"tr": "İstek modelin bağlam penceresine sığmadı. Daha az kaynak seçin ya da yeni bir sohbet başlatın.", "en": "The request did not fit the model's context window. Select fewer sources or start a new chat.", "zh": "请求超出了模型的上下文窗口。请减少所选资料或开始新对话。"},
    "err_provider": {"tr": "Model servisi bir sunucu hatası döndürdü. Biraz sonra tekrar deneyin.", "en": "The model service returned a server error. Try again shortly.", "zh": "模型服务返回了服务器错误，请稍后重试。"},
    "err_bad_request": {"tr": "Model servisi isteği kabul etmedi (HTTP {status}). Model ayarlarını kontrol edin.", "en": "The model service did not accept the request (HTTP {status}). Check the model settings.", "zh": "模型服务未接受该请求（HTTP {status}），请检查模型设置。"},
    "err_empty": {"tr": "Model boş yanıt döndürdü. Tekrar deneyin.", "en": "The model returned an empty response. Try again.", "zh": "模型返回了空响应，请重试。"},
    "err_unknown": {"tr": "Beklenmeyen bir hata oluştu. Ayrıntılar sunucu günlüğünde (Ayarlar → Sistem durumu).", "en": "An unexpected error occurred. Details are in the server log (Settings → System status).", "zh": "发生意外错误。详情见服务器日志（设置 → 系统状态）。"},
    "test_failed": {"tr": "Bağlantı testi başarısız: {reason}", "en": "Connection test failed: {reason}", "zh": "连接测试失败：{reason}"},
    "message_not_found": {"tr": "Mesaj bulunamadı", "en": "Message not found", "zh": "消息不存在"},
    "message_not_in_session": {"tr": "Mesaj bu sohbete ait değil", "en": "The message does not belong to this chat", "zh": "消息不属于此会话"},
    "only_user_messages_editable": {"tr": "Yalnızca kullanıcı mesajları düzenlenebilir", "en": "Only user messages can be edited", "zh": "只能编辑用户消息"},
    "export_failed": {"tr": "Dışa aktarma başarısız; lütfen tekrar deneyin", "en": "Export failed; please try again", "zh": "导出失败，请重试"},
}
