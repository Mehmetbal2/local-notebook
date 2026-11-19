# Değişiklik Günlüğü

Bu projedeki önemli değişiklikler bu dosyada tutulur. Sürüm numaraları [Anlamsal Sürümleme](https://semver.org/lang/tr/) kuralına uyar.

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
