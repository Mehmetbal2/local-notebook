# Değişiklik Günlüğü

Bu projedeki önemli değişiklikler bu dosyada tutulur. Sürüm numaraları [Anlamsal Sürümleme](https://semver.org/lang/tr/) kuralına uyar.

## [Yayımlanmadı]

### Güvenlik
- Yüklenen dosyaların, web kaynaklarının ve görsellerin yolları artık yükleme klasörünün dışına çıkamaz (`safe_join`); proje silinirken klasör yolu da aynı şekilde denetlenir.
- Derin araştırma raporlarındaki `[S1, S2]` kaynak işaretlerini çözen düzenli ifade, özel hazırlanmış metinlerde üstel sürede çalışabiliyordu; düzeltildi. Not başlığı ve markdown blok (başlık, liste, tablo) desenleri de geri izlemeye kapalı hale getirildi.
- Oluşturulan yönetici parolası hiçbir durumda günlüğe yazılmaz; parola dosyası yazılamazsa uygulama değişikliği kaydetmeden, açıklayıcı bir hatayla durur.
- Şifre değiştirildiğinde ya da yönetici sıfırladığında kullanıcının eski oturumları (erişim ve yenileme anahtarları) anında geçersiz olur. Bu sürüme geçince herkesin bir kez yeniden giriş yapması gerekir.
- Web kaynağı içe aktarma ve web araması artık yalnızca genel internetteki adresleri indirir; yerel ağ, sunucunun kendisi ve bulut meta veri adresleri (yönlendirmeler dahil) engellenir. Güvenilir tek kullanıcılı kurulumda `WEB_FETCH_ALLOW_PRIVATE=1` ile açılabilir.
- Dosya yüklemelerinde oturum ve boyut sınırı (`MAX_UPLOAD_MB`, varsayılan 500 MB) gövde okunmadan denetlenir; oturum açmamış biri sunucu diskini dolduramaz.
- Açıldığında aşırı büyüyen EPUB/DOCX dosyaları ("zip bombası") işlenmez (`ARCHIVE_MAX_UNCOMPRESSED_MB`, varsayılan 512 MB).
- DOCX dışa aktarımında markdown görsel bağlantıları artık sunucudaki dosyaları belgeye gömemez.
- `[citation_0-citation_999999999]` gibi dev atıf aralıkları açılmaz; bellek tükenmesi önlendi.
- Docker Compose: Redis ve Milvus yalnızca `127.0.0.1` üzerinden yayınlanır (parolasız Redis üzerinden kod çalıştırma ve Milvus'a doğrudan erişim engellendi).
- Sohbet ve bağlantı testi hataları kullanıcıya hatanın türüyle (zaman aşımı, bağlantı, API anahtarı, kota, bağlam penceresi…) bildirilir; ayrıntılar yalnızca sunucu günlüğünde kalır. Kimlik doğrulamasız `/health/redis` uç noktası hata metni döndürmez.

## [1.0.0] - 2026-11-19

Local Notebook'un ilk kararlı sürümü: bilgisayarınızda çalışan, yanıtlarını paragraf düzeyinde kaynağına bağlayan bir araştırma not defteri.

### Kaynaklar ve arama
- PDF, DOCX, DOC, TXT, MD, HTML, EPUB, görsel ve ses dosyalarından kaynak ekleme; panodan metin yapıştırma.
- PDF'lerde özgün görünüm ile ayrıştırılmış metin arasında geçiş; formüllerin (KaTeX) bütün olarak gösterilmesi.
- Çok dilli yerel gömme modeli **bge-m3** (uygulama tarafından otomatik başlatılır) veya OpenAI uyumlu bir gömme API'si.
- Büyük-küçük harf, aksan ve harekeden bağımsız arama ("maverdi" → "Mâverdî").
- Kaynak adları için "Yazar - Yıl - Eser" önerisi.
- Web ve akademik arama: hızlı arama (Tam metin / Açık erişim / Yalnızca özet etiketleriyle) ve atıflı derin araştırma raporları.

### Sohbet ve çıktılar
- Her iddianın kaynağındaki paragrafa götüren atıflarla sohbet; otomatik sohbet başlıkları.
- Öğrenme ve analiz araçları (çalışma rehberi, bilgi kartları, sınav, SSS, zihin haritası, zaman çizelgesi, brifing, podcast, karşılaştırmalı analiz ve özel araçlar), kapsamlı raporlar ve notlar.
- Sohbetleri ve raporları Word belgesi olarak dışa aktarma.

### Yönetim ve işletim
- Çok kullanıcılı kullanım ve yönetici için kullanıcı istatistikleri.
- **Ayarlar → Sistem durumu:** model kullanımı, tek tıkla yedek indirme ve geri yükleme, servislerin ve son hataların anlık durumu.
- Gömme modeli değişince vektörlerin metinler ve özetler korunarak otomatik yeniden oluşturulması.
- Güvenilirlik: geçici hatalarda yeniden deneme; gömme hatasında LLM özetlerinin tekrar üretilmemesi; SQLite WAL.
- Güvenli varsayılanlar: rastgele yönetici şifresi, kalıcı gizli anahtar, yerel ağla sınırlı CORS.
- Türkçe, İngilizce ve Çince arayüz.

### Geliştirme
- GitHub Actions'ta arka uç testleri ve arayüz derlemesi; CodeQL ve Dependabot.

Local Notebook, [chatboxai/local-notebook](https://github.com/chatboxai/local-notebook) temel alınarak geliştirilmiştir (Apache-2.0); bkz. [NOTICE](https://github.com/Mehmetbal2/local-notebook/blob/main/NOTICE).

[1.0.0]: https://github.com/Mehmetbal2/local-notebook/releases/tag/v1.0.0
