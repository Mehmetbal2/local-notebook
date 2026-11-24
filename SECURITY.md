# Güvenlik Politikası

<p><b>Türkçe</b> · <a href="#security-policy-english">English</a></p>

Local Notebook, belgelerinizi kendi bilgisayarınızda işleyen bir uygulamadır. Bu belge hangi sürümlerin desteklendiğini, bir güvenlik açığını nasıl bildireceğinizi ve uygulamanın hangi güvenlik varsayımlarıyla tasarlandığını anlatır.

## Desteklenen sürümler

| Sürüm | Destek |
|---|---|
| `main` dalının son hâli | ✅ Güvenlik düzeltmeleri yapılır |
| Daha eski commit'ler | ❌ Lütfen önce güncelleyin |

Henüz numaralı sürüm yayımlanmıyor; düzeltmeler doğrudan `main` dalına gelir.

## Güvenlik açığı bildirme

**Lütfen güvenlik açıklarını herkese açık bir issue olarak açmayın.**

1. Repodaki **Security → Report a vulnerability** bağlantısıyla gizli bir bildirim oluşturun.
2. Bildirimde şunlar olsun: etkilenen bileşen (arka uç, arayüz, betikler, yerel servisler), yeniden üretme adımları, beklenen ve gerçekleşen davranış, etkisi ve varsa önerdiğiniz çözüm.
3. Gerçek kişisel verileri, API anahtarlarını veya başkalarına ait belgeleri bildirime eklemeyin.

Bu projeyi tek bir geliştirici sürdürüyor. Hedeflerimiz:

- bildirimi **7 gün** içinde yanıtlamak,
- etkisini **14 gün** içinde değerlendirip size bildirmek,
- ciddi açıkları düzeltmeyi **30 gün** içinde yayımlamak.

Düzeltme yayımlanana kadar ayrıntıları paylaşmamanızı rica ederiz. İsterseniz düzeltme notunda adınız teşekkürle anılır.

## Güvenlik modeli

Local Notebook **tek bir bilgisayarda veya güvenilen bir yerel ağda** çalışmak üzere tasarlanmıştır; internete doğrudan açılacak bir sunucu olarak sertleştirilmemiştir.

- **İnternete açmayın.** Arayüz (8080) ve arka uç (8081) bağlantı noktalarını modem veya bulut sunucusu üzerinden dışarıya yönlendirmeyin. Uzaktan erişim gerekiyorsa VPN ya da TLS kullanan, kimlik doğrulamalı bir ters vekil sunucu (reverse proxy) kullanın.
- **Veri klasörünü koruyun.** `local-notebook-data/` içinde veritabanı, yüklenen belgeler, vektörler, yedekler ve **düz metin olarak saklanan LLM API anahtarları** bulunur. Bu klasör şifrelenmez; disk şifrelemesi (macOS'ta FileVault) kullanmanızı öneririz.
- **Dış servislere ne gider?** Bulut LLM veya gömme API'si kullanırsanız sorularınız ve ilgili belge parçaları o sağlayıcıya gönderilir. Web aramaları yerel SearXNG üzerinden arama motorlarına iletilir. Tamamen yerel çalışmak için yerel gömme servisi ve Ollama/vLLM gibi yerel bir model kullanın.

## Yerleşik korumalar

- **Kimlik doğrulama:** Giriş, sağlık kontrolü ve tek kullanımlık yedek bağlantıları dışındaki bütün API uçları JWT ister; kullanıcı yönetimi yalnızca yöneticiye açıktır.
- **Varsayılan şifre yok:** İlk açılışta rastgele bir yönetici şifresi oluşturulur ve yalnızca sahibinin okuyabileceği `admin_password.txt` dosyasına yazılır.
- **Kalıcı gizli anahtar:** `SECRET_KEY` boşsa veya örnek değerse kalıcı, rastgele bir anahtar üretilir.
- **CORS:** Yalnızca `localhost` ve özel yerel ağ adresleri kabul edilir.
- **Yüklenen HTML:** Tarayıcıda çalıştırılmaz; düz metin olarak, indirme şeklinde sunulur.
- **Yedekler:** Tek kullanımlık, kısa ömürlü bağlantılarla indirilir; indirilmeyen arşivler otomatik silinir.
- **Oturumlar:** Şifre değiştiğinde veya yönetici tarafından sıfırlandığında o kullanıcının eski bütün oturumları (erişim ve yenileme anahtarları) hemen geçersiz olur.
- **Web'den indirme:** Web kaynağı içe aktarma ve web araması yalnızca genel internetteki adreslere gider; yerel ağ, sunucunun kendisi ve bulut meta veri adresleri (yönlendirmeler dahil) engellenir.
- **Yüklemeler:** Dosya gövdesi okunmadan önce geçerli oturum ve boyut sınırı (`MAX_UPLOAD_MB`) denetlenir; açıldığında aşırı büyüyen EPUB/DOCX arşivleri işlenmez.
- **Docker:** Redis ve Milvus yalnızca `127.0.0.1` üzerinden yayınlanır.
- **Repo güvenliği:** GitHub Actions testleri, CodeQL taraması, Dependabot bağımlılık uyarıları ve gizli bilgi taraması için `.gitleaks.toml` yapılandırması.

## Kapsam

**Kapsamda:** bu repodaki arka uç, arayüz, `start.sh` ve diğer betikler, `services/` altındaki yerel servisler, varsayılan yapılandırma.

**Kapsam dışı:**

- uygulamayı bu belgeye aykırı biçimde internete açmaktan doğan sorunlar,
- veri klasörüne zaten erişimi olan birinin yapabildikleri,
- üçüncü taraf hizmetlerdeki (LLM sağlayıcıları, arama motorları, SearXNG, Milvus) açıklar; bunları ilgili projeye bildirin. Local Notebook'un bu bileşenleri güvensiz kullanması ise kapsamdadır.

---

<a id="security-policy-english"></a>

# Security Policy (English)

Local Notebook processes your documents on your own computer. This document covers supported versions, how to report a vulnerability, and the security assumptions behind the application.

## Supported versions

| Version | Supported |
|---|---|
| Latest `main` | ✅ Receives security fixes |
| Older commits | ❌ Please update first |

There are no numbered releases yet; fixes land directly on `main`.

## Reporting a vulnerability

**Please do not report security issues in public issues.**

1. Open a private report with **Security → Report a vulnerability** in this repository.
2. Include the affected component, steps to reproduce, expected and actual behaviour, impact, and a suggested fix if you have one.
3. Do not attach real personal data, API keys or other people's documents.

The project has a single maintainer. We aim to acknowledge reports within **7 days**, share an assessment within **14 days**, and release fixes for serious issues within **30 days**. Please keep details private until a fix is released; you will be credited in the fix notes if you wish.

## Security model

Local Notebook is designed to run **on one computer or a trusted local network**. It is not hardened as an internet-facing server.

- **Do not expose it to the internet.** Do not forward the interface (8080) or backend (8081) ports. For remote access use a VPN or an authenticating reverse proxy with TLS.
- **Protect the data folder.** `local-notebook-data/` holds the database, uploads, vectors, backups and **LLM API keys stored in plain text**. It is not encrypted; use full-disk encryption (FileVault on macOS).
- **What leaves your machine.** With a cloud LLM or embedding API, your questions and the relevant passages are sent to that provider. Web searches go through the local SearXNG to public search engines. For fully local operation use the local embedding service and a local model (Ollama, vLLM).

## Built-in protections

- JWT authentication on every API route except login, health checks and one-time backup links; user management is admin-only.
- No default password: a random admin password is generated on first start and written to an owner-only `admin_password.txt`.
- A persistent random secret key replaces a missing or placeholder `SECRET_KEY`.
- CORS accepts only `localhost` and private LAN addresses.
- Uploaded HTML is served as a plain-text download, never rendered.
- Backups download through one-time, short-lived links; unfetched archives are removed.
- Changing or resetting a password immediately revokes all of that user's earlier access and refresh tokens.
- Web-source import and web search fetch only public internet addresses; loopback, private networks and cloud metadata endpoints are blocked, including through redirects.
- Uploads: a valid session and the size limit (`MAX_UPLOAD_MB`) are checked before the body is read; EPUB/DOCX archives that would expand to an unreasonable size are refused.
- Docker: Redis and Milvus are published on `127.0.0.1` only.
- Repository: GitHub Actions tests, CodeQL scanning, Dependabot alerts and a `.gitleaks.toml` secret-scanning configuration.

## Scope

**In scope:** the backend, interface, `start.sh` and other scripts, the local services in `services/`, and the default configuration.

**Out of scope:** problems caused by exposing the app to the internet against this guidance; actions by someone who already has access to the data folder; vulnerabilities in third-party services (LLM providers, search engines, SearXNG, Milvus), which should be reported upstream. Insecure use of those components by Local Notebook is in scope.
