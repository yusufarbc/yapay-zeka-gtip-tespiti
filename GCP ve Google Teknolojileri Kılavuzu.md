# **Google Cloud Platform ve Bağlantılı Google Teknolojileri Ekosistemi Teknik Kılavuz ve Mimari Envanter Raporu**

## **1\. Yapay Zeka, Makine Öğrenmesi ve Üretken Yapay Zeka (AI, Machine Learning & Generative AI)**

### **Vertex AI Agent Builder**

#### **1\. Ne Nedir?**

Vertex AI Agent Builder, kurumsal sistemlerde karmaşık ve otonom iş süreçlerini uçtan uca koordine etmek üzere tasarlanmış, üretken yapay zeka tabanlı ajanların (agents) geliştirilmesini sağlayan kapsamlı bir orkestrasyon platformudur1. Platform, düşük kodlu görsel geliştirme arayüzleri ile kod öncelikli kütüphaneleri bir araya getirerek modern yapay zeka iş gücü tasarımını standartlaştırır2.

#### **2\. Ne İşe Yarar?**

Geleneksel sohbet robotlarının esnek olmayan ve önceden tanımlanmış kurallara bağımlı yapısını aşarak, kullanıcı niyetini anlayan, dinamik kararlar alabilen ve harici sistemlerle güvenli etkileşim kuran sistemler sunar2. Geliştiricilere deterministik iş mantığı ile olasılıksal akıl yürütme süreçlerini güvenli ve yönetilebilir bir katmanda birleştirme olanağı tanır5.

#### **3\. Nasıl Kullanılır?**

Sistem, Python, Go veya Java tabanlı Agent Development Kit (ADK) kütüphaneleri ve yönetilen Agent Engine çalışma zamanı mimarisi üzerinde yükselir2. Girdi olarak kullanıcıların doğal dil talepleri alınırken, sistem bu talepleri Memory Bank ve bağlam katmanları (Static, Turn, User, Cache) ile işleyerek optimize eder2. Çıktı olarak anlamsal olarak doğrulanmış cevaplar, harici API çağrıları veya veritabanı eylemleri üretilir4.

#### **4\. Tipik Kullanım Senaryoları**

Çok adımlı müşteri destek operasyonları, şirket içi büyük bilgi tabanlarında semantik kurumsal aramaların yönetilmesi, tedarik ve fatura süreçlerinin otonom orkestrasyonu gibi karmaşık karar mekanizmaları gerektiren durumlarda tercih edilmelidir3.

#### **5\. Ekosistem Entegrasyonu**

BigQuery, Google Maps, Apigee API Hub, Cloud Storage, Google Workspace ve Vertex AI Search ile doğrudan yerleşik entegrasyonlara sahiptir3.

### **Vertex AI Search & Conversation**

#### **1\. Ne Nedir?**

Vertex AI Search & Conversation, işletmelerin sahip olduğu yapılandırılmamış ve yarı yapılandırılmış veriler üzerinde anlamsal arama motorları ve akıllı konuşma arayüzleri oluşturmasını sağlayan, evrimsel süreçte Vertex AI Agent Builder şemsiyesi altında birleştirilmiş bir temel yapay zeka servisidir7.

#### **2\. Ne İşe Yarar?**

Kurumsal dokümanlar, web sayfaları ve veri tabanları üzerinde klasik anahtar kelime aramalarının ötesine geçerek semantik ve bağlamsal arama yapılmasını sağlar6. Bilgiye dayalı üretim (RAG) süreçlerinin sıfırdan kod yazmaya gerek kalmadan dakikalar içinde kurulmasına olanak tanır7.

#### **3\. Nasıl Kullanılır?**

Geliştiriciler kurumsal veri kaynaklarını (PDF belgeleri, web siteleri, veritabanı tabloları) birer veri deposu (Data Store) olarak sisteme bağlarlar6. Girdi olarak kullanıcıların doğal dildeki karmaşık sorguları alınır; sistem bu sorguyu veritabanındaki indekslenmiş anlamsal temsillerle eşleştirerek çıktı olarak en alakalı bilgi parçacıklarını ve özetlenmiş yanıtları üretir6.

#### **4\. Tipik Kullanım Senaryoları**

Kurum içi teknik dokümantasyon merkezlerinde akıllı arama asistanlarının kurulması, e-ticaret sitelerinde müşteri sorularına ürün kılavuzlarından anlık yanıtlar üreten sistemlerin tasarlanması durumlarında tercih edilir3.

#### **5\. Ekosistem Entegrasyonu**

Cloud Storage, BigQuery, Dialogflow, Vertex AI Agent Builder ve Vertex AI Vector Search ile kesintisiz veri ve servis entegrasyonu sunar3.

### **Vertex AI Vector Search**

#### **1\. Ne Nedir?**

Vertex AI Vector Search, milyarlarca yüksek boyutlu vektör (embedding) üzerinde ultra düşük gecikme ve yüksek doğrulukla benzerlik araması (Approximate Nearest Neighbor \- ANN) gerçekleştirebilen, tamamen yönetilen bir vektör veritabanı altyapısıdır4.

#### **2\. Ne İşe Yarar?**

Yapılandırılmamış verilerin (görsel, ses, doğal dil metinleri) matematiksel özetleri olan vektörler arasında saniyeler altında arama yapma problemini çözer. Çok büyük veri kümelerinde bile milisaniyeler mertebesinde anlamsal eşleştirmeler gerçekleştirerek ölçeklenebilir yapay zeka sistemlerinin temelini oluşturur.

#### **3\. Nasıl Kullanılır?**

Bir embedding modeli tarafından üretilen yüksek boyutlu vektörler Cloud Storage üzerinde depolanarak Vector Search dizinine aktarılır. Arama esnasında girdi olarak hedef sorgunun vektör temsili gönderilir. Sistem, gelişmiş benzerlik algoritmalarını kullanarak dizini tarar ve en yakın komşu vektör kümesini ilişkili meta verileriyle birlikte çıktı olarak döndürür.

#### **4\. Tipik Kullanım Senaryoları**

Büyük dil modellerinin doğrulanmış kurumsal veriyle beslenmesi (RAG) mimarilerinde hızlı veri erişim katmanı olarak, e-ticaret sitelerinde görsel tabanlı ürün arama ve benzer ürün öneri motorlarında tercih edilir4.

#### **5\. Ekosistem Entegrasyonu**

Vertex AI Agent Builder, Cloud Storage, BigQuery, Vertex AI Workbench, Cloud SQL ve AlloyDB ile doğrudan konuşur4.

### **Vertex AI Workbench**

#### **1\. Ne Nedir?**

Vertex AI Workbench, veri bilimcilerinin veri keşfi yapması, makine öğrenmesi modelleri tasarlaması, eğitmesi ve üretime alması için optimize edilmiş, JupyterLab tabanlı, tamamen yönetilen ve güvenli bir geliştirme ortamıdır12.

#### **2\. Ne İşe Yarar?**

Veri bilimi ekiplerinin yerel makinelerinde karşılaştığı hesaplama gücü yetersizliği, kütüphane uyumsuzlukları ve veritabanı bağlantı karmaşasını çözer. Tek tıkla ölçeklenebilen donanım desteği ve kurumsal güvenlik standartları sunarak veri hazırlığından model dağıtımına kadar geçen süreyi önemli ölçüde kısaltır.

#### **3\. Nasıl Kullanılır?**

Kullanıcılar GCP Konsolu üzerinden bir Workbench örneği başlatırlar. Girdi olarak BigQuery veri ambarından çekilen SQL tabloları veya Cloud Storage üzerindeki veri kümeleri kullanılır. Notebook üzerinde yazılan Python veya SQL kodları çalıştırılarak veri analizi yapılır, modeller eğitilir ve çıktı olarak model dosyaları, görselleştirmeler ya da Vertex AI Model Registry'ye kaydedilmeye hazır makine öğrenmesi modelleri üretilir.

#### **4\. Tipik Kullanım Senaryoları**

Keşifsel veri analizi (EDA), özel makine öğrenmesi modellerinin prototiplenmesi, büyük veri setleri üzerinde veri temizleme işlemleri ve makine öğrenmesi ardışık düzenlerinin orkestrasyonu için tercih edilir.

#### **5\. Ekosistem Entegrasyonu**

BigQuery, Cloud Storage, Dataproc, Vertex AI Training, Artifact Registry ve Cloud IAM ile doğrudan entegrasyona sahiptir12.

### **Gemini Modelleri (Flash, Pro, Ultra, Flash-Lite)**

#### **1\. Ne Nedir?**

Gemini, Google'ın yerel olarak çok modlu (native multimodal) olarak tasarlanmış, metin, kod, ses, görüntü ve video girdilerini eşzamanlı olarak işleyebilen yeni nesil gelişmiş yapay zeka temel model ailesidir2. Model ailesi; en yüksek karmaşıklıktaki analizler için Ultra, geniş ölçekli genel görevler için Pro, yüksek hız ve verimlilik için Flash ve ultra düşük gecikme ile bütçe dostu operasyonlar için tasarlanan Flash-Lite modellerini içerir13.

#### **2\. Ne İşe Yarar?**

Farklı veri türlerinin işlenmesi için ayrı ayrı modeller kullanma zorunluluğunu ve bu süreçteki veri kaybı problemini ortadan kaldırır4. Özellikle Gemini 3.1 Flash-Lite, yüksek hacimli kurumsal iş akışlarında karşılaşılan yüksek çıkarım maliyetleri ve gecikme (latency) problemlerini radikal biçimde düşürerek saniyeler altı gecikme süreleriyle çalışabilme avantajı sağlar13.

#### **3\. Nasıl Kullanılır?**

Geliştiriciler Vertex AI API'leri veya Google AI Studio üzerinden modellere erişirler14. Girdi olarak tek bir istem (prompt) içinde metin, kod, yüksek çözünürlüklü görseller veya saatlerce süren ses/video dosyaları gönderilebilir4. Model, bu girdileri ortak bir çok modlu uzayda işler; çıkarım yaparak yapılandırılmış metinler, kod blokları, anlamsal analizler ya da duygu durumlu ses çıktıları üretir4.

#### **4\. Tipik Kullanım Senaryoları**

Gemini Ultra derin akademik araştırmalar ve karmaşık kod analizlerinde; Gemini Pro genel amaçlı çok modlu akıl yürütme süreçlerinde; Gemini Flash hızlı veri özetleme ve içerik üretiminde; Gemini Flash-Lite ise yüksek hacimli gerçek zamanlı sohbet robotlarında ve anlık araç çağırma işlemlerinde tercih edilmelidir13.

#### **5\. Ekosistem Entegrasyonu**

Vertex AI Agent Builder, BigQuery, Cloud Run, Cloud Run Functions, Apigee ve Google Security Operations ile uçtan uca entegre çalışır4.

### **Document AI**

#### **1\. Ne Nedir?**

Document AI, taranmış belgeleri, PDF'leri ve resimleri analiz ederek yapılandırılmamış verileri makine tarafından okunabilir yapılandırılmış verilere dönüştüren makine öğrenmesi tabanlı bir belge işleme platformudur16.

#### **2\. Ne İşe Yarar?**

Faturalar, makbuzlar, sözleşmeler ve kimlik belgeleri gibi manuel veri girişi gerektiren süreçlerdeki operasyonel yükü ve insan hatası riskini ortadan kaldırır. Gelişmiş optik karakter tanıma (OCR) ve doğal dil işleme (NLP) teknolojileriyle belgelerin anlamsal bütünlüğünü koruyarak veri çıkarımı sağlar.

#### **3\. Nasıl Kullanılır?**

Belgeler API uç noktasına veya bir Cloud Storage klasörüne yüklenir (girdi). Document AI, önceden eğitilmiş veya özel olarak yapılandırılmış belge işlemcilerini kullanarak belgeyi tarar, sınıflandırır ve ilgili alanları anahtar-değer çiftleri halinde ayıklar. Çıktı olarak, hedef sistemlerin doğrudan işleyebileceği temiz bir JSON veri yapısı sunulur.

#### **4\. Tipik Kullanım Senaryoları**

Finans departmanlarında fatura onay süreçlerinin otomasyonu, insan kaynaklarında kimlik ve pasaport bilgilerinin otomatik doğrulanması, lojistik sektöründe taşıma belgelerinden veri çıkarılması gibi senaryolarda tercih edilir3.

#### **5\. Entegrasyon Yapısı**

Cloud Storage, Cloud Run Functions, BigQuery, AppSheet ve Cloud Build ile doğrudan entegrasyona sahiptir16.

### **Translation API**

#### **1\. Ne Nedir?**

Translation API, Google'ın gelişmiş sinirsel makine çevirisi (NMT) teknolojisini kullanarak metinleri dinamik olarak yüzden fazla dil arasında yüksek doğrulukla çeviren küresel bir bulut servisidir14.

#### **2\. Ne İşe Yarar?**

Küresel operasyonlar yürüten işletmelerin, farklı dillerdeki kullanıcılarla gerçek zamanlı ve anlamsal olarak doğru bir şekilde iletişim kurmasını sağlar. Statik çevirilerin aksine, dilin bağlamını ve sektörel terminolojiyi algılayarak çeviri kalitesini artırır.

#### **3\. Nasıl Kullanılır?**

Uygulama kodundan REST veya gRPC protokolü üzerinden API'ye bir metin gönderilir (girdi). API, kaynak dili otomatik olarak algılayabilir veya hedef dil belirtilebilir. Çeviri motoru metni işler ve milisaniyeler içinde hedef dildeki karşılığını (çıktı) uygulamaya döndürür.

#### **4\. Tipik Kullanım Senaryoları**

E-ticaret sitelerinde ürün açıklamalarının dinamik olarak yerelleştirilmesi, uluslararası müşteri destek platformlarında gelen mesajların anlık çevrilmesi ve çok dilli içerik yönetim sistemlerinin otomasyonu için tercih edilir13.

#### **5\. Ekosistem Entegrasyonu**

Vertex AI Agent Builder, Cloud Run, Cloud Run Functions, BigQuery ve Google Workspace API'leri ile entegre çalışır3.

### **Vision API**

#### **1\. Ne Nedir?**

Vision API, geliştiricilerin önceden eğitilmiş güçlü makine öğrenmesi modellerini uygulamalarına entegre ederek görsellerin içeriğini anlamlandırmalarını sağlayan bir bilgisayarlı görü (computer vision) servisidir13.

#### **2\. Ne İşe Yarar?**

Görsellerin manuel olarak etiketlenmesi, sınıflandırılması veya uygunsuz içeriklerin denetlenmesi gibi yüksek iş gücü gerektiren problemleri otomatikleştirir. Görsellerdeki nesneleri, yüzleri, logoları ve yazıları milisaniyeler içinde algılayarak uygulamalara görsel zeka kazandırır13.

#### **3\. Nasıl Kullanılır?**

Bir görsel dosyası veya Cloud Storage üzerindeki bir görsel adresi API'ye gönderilir (girdi). Vision API, görseli analiz ederek algılanan nesnelerin koordinatlarını, baskın renkleri, metinleri (OCR) ve içerik güvenliği skorlarını içeren detaylı bir JSON nesnesini çıktı olarak döndürür13.

#### **4\. Tipik Kullanım Senaryoları**

Kullanıcılar tarafından yüklenen profil fotoğraflarının veya içeriklerin otomatik denetlenmesi (safe search), depolarda barkod ve ürün etiketlerinin taranması, görsel arama motorlarının tasarlanması durumlarında tercih edilir13.

#### **5\. Ekosistem Entegrasyonu**

Cloud Storage, Cloud Run, Pub/Sub, BigQuery ve Firebase Platformu ile tam uyumlu çalışır16.

### **Speech-to-Text**

#### **1\. Ne Nedir?**

Speech-to-Text, Google'ın gelişmiş derin öğrenme sinir ağı algoritmalarını kullanarak ses kayıtlarını veya canlı konuşmaları gerçek zamanlı olarak metne dönüştüren güçlü bir ses tanıma servisidir.

#### **2\. Ne İşe Yarar?**

Sesli verilerin manuel olarak deşifre edilmesi zorluğunu ortadan kaldırır. 125'ten fazla dili ve lehçeyi destekleyerek, gürültülü ortamlarda veya birden fazla konuşmacının olduğu ses kayıtlarında bile yüksek doğruluk oranlarıyla çalışır.

#### **3\. Nasıl Kullanılır?**

Bir ses dosyası veya canlı ses akışı (streaming) API'ye aktarılır (girdi). API, ses sinyallerini işler, kelime sınırlarını belirler, konuşmacıları ayrıştırır (diarization) ve zaman damgaları ile birlikte dönüştürülmüş metni çıktı olarak uygulamaya teslim eder.

#### **4\. Tipik Kullanım Senaryoları**

Çağrı merkezlerindeki müşteri görüşmelerinin kalite kontrol amacıyla metne dönüştürülüp analiz edilmesi, video içeriklerine otomatik altyazı eklenmesi ve sesle kontrol edilen akıllı asistanların geliştirilmesi durumlarında kullanılır.

#### **5\. Ekosistem Entegrasyonu**

Dialogflow, Cloud Storage, Dataflow, Vertex AI Agent Builder ve Cloud Logging ile doğrudan konuşur4.

### **Text-to-Speech**

#### **1\. Ne Nedir?**

Text-to-Speech, yazılı metinleri Google'ın yapay zeka ve DeepMind WaveNet/Gemini teknolojilerini kullanarak insan sesine en yakın, doğal ve akıcı bir biçimde sese dönüştüren bir sentezleme servisidir15.

#### **2\. Ne İşe Yarar?**

Uygulamaların kullanıcılarla sesli iletişim kurmasını sağlayarak erişilebilirliği artırır ve daha etkileşimli kullanıcı deneyimleri sunar. Gemini 3.1 Flash TTS gibi yeni nesil modeller, konuşma hızı, tonlama, vurgu ve duygusal durumlar üzerinde milisaniyelik hassasiyetle kontrol imkanı tanır15.

#### **3\. Nasıl Kullanılır?**

Uygulama, seslendirilmek istenen metni ve tercih edilen ses/dil parametrelerini API'ye iletir (girdi). Gelişmiş modellerde metin içine yerleştirilen \[whispers\] veya \[laughs\] gibi ses etiketleri (audio tags) ile tonlama doğrudan yönlendirilebilir15. API, bu yönergeleri işleyerek MP3 veya WAV formatında yüksek kaliteli bir ses dosyasını çıktı olarak üretir15.

#### **4\. Tipik Kullanım Senaryoları**

Sesli kitap ve makale okuma uygulamaları, akıllı ev asistanları, çağrı merkezleri için otomatik sesli yanıt (IVR) sistemleri ve interaktif oyun karakterlerinin seslendirilmesi süreçlerinde tercih edilir15.

#### **5\. Ekosistem Entegrasyonu**

Dialogflow, Cloud Run, Cloud Run Functions, Firebase ve Google Workspace API'leri ile entegre çalışır16.

### **Cloud TPU**

#### **1\. Ne Nedir?**

Cloud TPU (Tensor Processing Unit), Google tarafından makine öğrenmesi ve yapay zeka modellerinin eğitimi ile çıkarım (inference) süreçlerini hızlandırmak amacıyla özel olarak geliştirilmiş olan tescilli entegre devrelerdir (ASIC)19.

#### **2\. Ne İşe Yarar?**

Milyarlarca parametreye sahip modern derin öğrenme modellerinin geleneksel işlemcilerle (CPU/GPU) eğitilmesi sırasında karşılaşılan yüksek zaman ve enerji maliyetlerini çözer. Matris çarpım işlemlerini donanımsal düzeyde paralel olarak işleyerek eğitim sürelerini haftalardan saatlere indirir.

#### **3\. Nasıl Kullanılır?**

Geliştiriciler TensorFlow, PyTorch veya JAX kütüphanelerini kullanarak yazdıkları modelleri Compute Engine veya GKE üzerinde çalışan TPU podlarına yönlendirirler19. Girdi olarak terabaytlarca büyüklükteki veri setleri sisteme verilir. Donanım, veriyi paralel matris işlemcilerinde işleyerek çıktı olarak optimize edilmiş model ağırlık dosyalarını üretir.

#### **4\. Tipik Kullanım Senaryoları**

Sıfırdan büyük dil modellerinin (LLM) eğitilmesi, devasa görüntü tanıma modellerinin optimize edilmesi ve yüksek ölçekli yapay zeka çıkarım sunucularının desteklenmesi durumlarında tercih edilir19.

#### **5\. Ekosistem Entegrasyonu**

Compute Engine, Google Kubernetes Engine, Cloud Storage, Filestore ve Vertex AI Training ile doğrudan entegrasyonu mevcuttur.

### **GPU Kümeleri (GPU Clusters)**

#### **1\. Ne Nedir?**

GPU Kümeleri, Google Cloud'un sanal makinelerine entegre edilebilen, NVIDIA'nın en gelişmiş grafik işlem birimlerini (A100, H100, L4) barındıran yüksek performanslı ve ölçeklenebilir hesaplama altyapısıdır19.

#### **2\. Ne İşe Yarar?**

Genel amaçlı yapay zeka eğitimleri, paralel hesaplama işleri ve özellikle gerçek zamanlı yapay zeka çıkarım (inference) süreçlerindeki yüksek işlem gücü gereksinimini karşılar. Bulut üzerinde esnek olarak ölçeklenebilen yapısı sayesinde donanım yatırım maliyetlerini (CapEx) işletme maliyetlerine (OpEx) dönüştürür20.

#### **3\. Nasıl Kullanılır?**

Kullanıcılar Compute Engine veya GKE üzerinde GPU destekli sanal makineler veya düğüm havuzları (node pools) oluştururlar19. Girdi olarak grafik işleme, 3D render veya derin öğrenme kodları sunulur. GPU'lar bu kodları paralel iş parçacıkları halinde saniyeler içinde işleyerek çıktı olarak sonuçları ekrana yansıtır veya depolama birimlerine yazar20.

#### **4\. Tipik Kullanım Senaryoları**

Büyük dil modellerinin gerçek zamanlı çıkarım (inference) süreçleri, yüksek çözünürlüklü video işleme ve dönüştürme (transcoding) ile karmaşık fiziksel simülasyonların çalıştırılması senaryolarında tercih edilmelidir20.

#### **5\. Ekosistem Entegrasyonu**

Compute Engine, GKE, Cloud Run, Artifact Registry, Cloud Storage ve Vertex AI ile entegre çalışır20.

## **2\. Sunucusuz Mimari, Hesaplama ve Konteyner Teknolojileri (Serverless, Compute & Containers)**

### **Compute Engine**

#### **1\. Ne Nedir?**

Compute Engine, Google Cloud Platform'un sunduğu, kullanıcıların sanal makineler (VM) oluşturup yönetmelerini sağlayan ölçeklenebilir ve güvenli bir Altyapı Servisidir (IaaS)19.

#### **2\. Ne İşe Yarar?**

Fiziksel sunucu tedarik etme, veri merkezi yönetme ve donanım bakım maliyetlerini ortadan kaldırır. İhtiyaca özel olarak yapılandırılabilen işlemci, bellek ve depolama seçenekleri sayesinde donanım kaynaklarının israf edilmesini engeller19.

#### **3\. Nasıl Kullanılır?**

Kullanıcılar konsol, gcloud CLI veya Terraform ile sanal makine şablonları belirler23. Girdi olarak işletim sistemi imajı, disk türü (SSD/HDD) ve ağ kuralları girilir23. VM ayağa kalktığında, üzerine yüklenen kurumsal yazılımlar çalışmaya başlar ve ağ üzerinden gelen taleplere çıktı üreterek yanıt verir23.

#### **4\. Tipik Kullanım Senaryoları**

Geleneksel monolitik uygulamaların buluta taşınması (lift-and-shift), özel işletim sistemi ve çekirdek özelleştirmesi gerektiren iş yükleri ile lisanslı kurumsal veritabanlarının barındırılması durumlarında tercih edilir23.

#### **5\. Ekosistem Entegrasyonu**

VPC, Cloud Storage, Filestore, Cloud IAM, Secret Manager ve Cloud Load Balancing ile tam entegre çalışır12.

### **Cloud Run**

#### **1\. Ne Nedir?**

Cloud Run, konteyner haline getirilmiş uygulamaları altyapı yönetimi gerektirmeksizin çalıştıran, talebe göre saniyeler içinde otomatik olarak ölçeklenebilen, tamamen yönetilen sunucusuz bir hesaplama platformudur9.

#### **2\. Ne İşe Yarar?**

Geliştiricilerin Kubernetes gibi karmaşık konteyner orkestrasyon sistemlerini öğrenme ve yönetme zorunluluğunu ortadan kaldırır. Sıfıra ölçeklenme (scale-to-zero) yeteneği sayesinde, uygulama aktif istek almadığında hesaplama maliyetlerini tamamen sıfıra düşürür20.

#### **3\. Nasıl Kullanılır?**

Geliştirici, uygulamayı Docker konteyneri olarak paketler veya kaynak kodunu doğrudan platforma ileterek Buildpacks teknolojisiyle otomatik derlenmesini sağlar20. Girdi olarak HTTP istekleri veya sistem olayları alınır18. Cloud Run, gelen yükü karşılamak üzere konteyner kopyalarını anında çoğaltır ve çıktı olarak HTTP yanıtları üretir20.

#### **4\. Tipik Kullanım Senaryoları**

Web siteleri ve mikroservis mimarilerinin barındırılması, RESTful ve GraphQL API'lerinin sunulması, olay tetiklemeli arka plan veri işleme hatları ile zamanlanmış batch işlerinin (Cloud Run Jobs) koordine edilmesi durumlarında tercih edilir20.

#### **5\. Ekosistem Entegrasyonu**

Artifact Registry, Cloud Build, VPC, Cloud SQL, AlloyDB, Pub/Sub, Eventarc ve Vertex AI ile derin entegrasyona sahiptir9.

### **Cloud Run Functions (Cloud Functions)**

#### **1\. Ne Nedir?**

Cloud Run Functions, belirli bulut olaylarına veya HTTP isteklerine yanıt olarak çalışan tek amaçlı, hafif ve tamamen sunucusuz kod bloklarının (FaaS) çalıştırılmasını sağlayan yönetim platformudur16.

#### **2\. Ne İşe Yarar?**

Küçük bir kod parçasını veya basit bir entegrasyonu çalıştırmak için tam bir sunucu veya konteyner altyapısı kurma ve ayakta tutma israfını önler. Sadece kodun çalıştığı 100 milisaniyelik süreler bazında ücretlendirme yaparak yüksek bütçe tasarrufu sağlar16.

#### **3\. Nasıl Kullanılır?**

Geliştirici desteklenen bir programlama dilinde (Node.js, Python, Go vb.) sadece ilgili fonksiyonu yazar ve bir olay tetikleyicisi tanımlar18. Girdi olarak bir veritabanı değişikliği veya Cloud Storage'a yüklenen bir dosya gibi sistem olayları alınır16. Fonksiyon, bu girdiyi alır, idempotent (tekrarlanabilir) bir mantıkla işler ve çıktı olarak işlemi sonlandırır veya sonraki sistemleri tetikler16.

#### **4\. Tipik Kullanım Senaryoları**

Kullanıcılar dosya yüklediğinde otomatik küçük resim (thumbnail) oluşturulması, ödeme onay sistemleri için webhook entegrasyonları, gerçek zamanlı veri akışı filtreleme ve Firebase arka plan görevlerinin yürütülmesi senaryolarında tercih edilmelidir16.

#### **5\. Ekosistem Entegrasyonu**

Cloud Storage, Pub/Sub, Firestore, Eventarc, Firebase ve BigQuery ile doğrudan konuşur12.

### **Google Kubernetes Engine (GKE)**

#### **1\. Ne Nedir?**

Google Kubernetes Engine (GKE), açık kaynaklı konteyner orkestrasyon standardı olan Kubernetes'in Google'ın optimize edilmiş ağ ve sunucu altyapısı üzerinde çalışan, tamamen yönetilen kurumsal hizmetidir27.

#### **2\. Ne İşe Yarar?**

Büyük ölçekli konteyner kümelerini manuel olarak yönetmenin getirdiği ağ karmaşası, düğüm bakımı, güvenlik yamaları ve otomatik ölçeklendirme zorluklarını çözer. Autopilot modu ile küme altyapısının yönetimini tamamen Google'a devrederek işletim maliyetlerini düşürür.

#### **3\. Nasıl Kullanılır?**

Kullanıcılar Kubernetes manifest dosyalarını (YAML) veya Helm şablonlarını GKE kontrol düzlemine (control plane) gönderirler. GKE, girdi olan bu talimatları işleyerek konteynerlerin podlar halinde düğümler (nodes) üzerinde sağlıklı çalışmasını koordine eder. Girdi olarak gelen ağ trafiği, podlar arasında dengelenerek kullanıcılara kesintisiz uygulama çıktıları olarak sunulur.

#### **4\. Tipik Kullanım Senaryoları**

Yüzlerce mikroservisin karmaşık ağ ilişkileriyle çalıştığı geniş ölçekli kurumsal uygulamalar, hibrit/çoklu bulut mimarileri ve yapay zeka modellerinin dağıtık olarak eğitildiği yüksek performanslı sistemler için en ideal platformdur22.

#### **5\. Ekosistem Entegrasyonu**

Artifact Registry, Cloud Load Balancing, Cloud Storage, VPC, Cloud IAM, Secret Manager ve Cloud Monitoring ile uçtan uca entegre çalışır12.

### **App Engine**

#### **1\. Ne Nedir?**

App Engine, geliştiricilerin altyapı, işletim sistemi veya konteyner yapılandırmalarıyla ilgilenmeden doğrudan web uygulamaları ve mobil arka plan servisleri geliştirmelerini sağlayan öncü bir Platform Servisidir (PaaS)19.

#### **2\. Ne İşe Yarar?**

Uygulama barındırmak için sunucu kurulumu, SSL sertifikası yönetimi ve yük dengeleyici ayarlarının getirdiği zaman kaybını ortadan kaldırır. Standard ve Flexible olmak üzere iki farklı çalışma ortamı sunarak hızlı prototiplemeden küresel ölçekli üretime kadar sorunsuz geçiş sağlar.

#### **3\. Nasıl Kullanılır?**

Geliştirici, uygulamanın çalışacağı çalışma zamanını (runtime) belirten basit bir yapılandırma dosyası (app.yaml) hazırlar ve dağıtım komutunu çalıştırır. Girdi doğrudan uygulama kaynak kodudur. App Engine bu kodları paketler, çalıştırır ve gelen HTTP isteklerini karşılayarak dinamik web sayfaları veya API yanıtları (çıktı) üretir.

#### **4\. Tipik Kullanım Senaryoları**

Monolitik veya hafif mikroservis mimarili web siteleri, mobil uygulama arka uçları, prototipler ve hızlı bir şekilde pazara sunulması gereken SaaS uygulamaları için tercih edilir19.

#### **5\. Ekosistem Entegrasyonu**

Cloud SQL, Memorystore, Cloud Storage, Cloud IAM, Cloud Build ve Cloud Tasks ile doğrudan konuşur12.

## **3\. Veritabanı Sistemleri (Relational & NoSQL)**

### **Cloud Firestore**

#### **1\. Ne Nedir?**

Cloud Firestore, mobil, web ve sunucu tarafı geliştirmeleri için tasarlanmış, verileri hiyerarşik doküman/koleksiyon yapısında saklayan, esnek, ölçeklenebilir ve gerçek zamanlı senkronizasyon yeteneğine sahip NoSQL belge veritabanıdır28.

#### **2\. Ne İşe Yarar?**

Geleneksel veritabanlarının, istemciler ile veritabanı arasında sürekli bağlantı kurup anlık veri güncellemelerini yansıtmadaki yetersizliğini çözer. Çevrimdışı veri desteği sayesinde internet bağlantısı koptuğunda bile uygulamanın çalışmasını ve bağlantı geldiğinde verilerin otomatik senkronize edilmesini sağlar.

#### **3\. Nasıl Kullanılır?**

Veriler, anahtar-değer çiftlerinden oluşan dokümanlar halinde ve bu dokümanları gruplayan koleksiyonlarda saklanır. İstemci SDK'ları veya sunucu kütüphaneleri aracılığıyla veritabanına veri yazılır. Firestore, anlık dinleyiciler sayesinde değişen veriyi bağlı olan tüm istemcilere milisaniyeler içinde ileterek çıktıyı sunar.

#### **4\. Tipik Kullanım Senaryoları**

Anlık mesajlaşma ve sohbet uygulamaları, işbirlikçi canlı doküman düzenleme araçları, mobil oyunların kullanıcı profil ve skor tabloları ile çevrimdışı çalışma gereksinimi olan saha uygulamaları için idealdir.

#### **5\. Ekosistem Entegrasyonu**

Firebase Platformu, Cloud Run Functions, BigQuery ve Cloud IAM ile derin entegrasyona sahiptir16.

### **Cloud Spanner**

#### **1\. Ne Nedir?**

Cloud Spanner, ilişkisel veritabanı yapısını ve ACID uyumluluğunu, NoSQL sistemlerin yatay ölçeklenebilirliğiyle birleştiren, küresel ölçekte güçlü tutarlılık sunan, kurumsal düzeyde bir ilişkisel veritabanı servisidir23.

#### **2\. Ne İşe Yarar?**

Küresel çapta yaygın uygulamalarda karşılaşılan, yüksek ölçeklenebilirlik ile güçlü veri tutarlılığı arasındaki ödünleşim (CAP Teoremi) problemini ortadan kaldırır28. Google'ın TrueTime teknolojisini kullanarak dünya genelinde dağıtık sunucularda eşzamanlı ve çelişkisiz işlemler yapılmasını sağlar ve çoklu bölgede %99.999 kullanılabilirlik SLA'i sunar23.

#### **3\. Nasıl Kullanılır?**

Veritabanı şeması ilişkisel modelde tasarlanır ve GoogleSQL ya da PostgreSQL arayüzü ile sorgulanabilir12. Girdi olarak yoğun eşzamanlı yazma ve okuma işlemleri alınır23. Spanner, verileri otomatik olarak parçalara bölerek düğümler arasında dağıtır23. ACID işlemlerini Paxos konsensüs algoritması ile koordine ederek çıktı olarak küresel düzeyde tutarlı veriler döndürür23.

#### **4\. Tipik Kullanım Senaryoları**

Küresel finansal işlem ve bankacılık sistemleri, küresel e-ticaret envanter ve sipariş yönetim platformları ile geniş ölçekli lojistik ve tedarik zinciri takip sistemlerinde kullanılmalıdır23.

#### **5\. Ekosistem Entegrasyonu**

BigQuery, Dataflow, Cloud Storage, Cloud IAM ve Vertex AI ile doğrudan entegre çalışır12.

### **Cloud SQL**

#### **1\. Ne Nedir?**

Cloud SQL; MySQL, PostgreSQL ve SQL Server ilişkisel veritabanı motorlarını destekleyen, altyapı bakımı, yedekleme, replikasyon ve failover süreçlerini otomatikleştiren tamamen yönetilen bir veritabanı hizmetidir23.

#### **2\. Ne İşe Yarar?**

Geleneksel ilişkisel veritabanı sunucularını kurma, işletim sistemi yamalarını uygulama, disk doluluğunu izleme ve manuel yedek alma gibi yüksek zaman ve kaynak tüketen operasyonel problemleri ortadan kaldırır. Bölgesel yüksek kullanılabilirlik mimarilerini tek tıkla kurarak kesintisiz çalışma güvencesi sunar11.

#### **3\. Nasıl Kullanılır?**

Kullanıcılar istedikleri motoru seçerek bir örnek başlatır, işlemci, bellek ve depolama boyutunu belirler23. Standart veritabanı sürücüleri veya Cloud SQL Auth Proxy kullanılarak veritabanına bağlanılır23. Girdi olarak standart SQL sorguları ve veri manipülasyon talepleri alınır; çıktı olarak ilişkisel veri kümeleri döndürülür12.

#### **4\. Tipik Kullanım Senaryoları**

Genel amaçlı web uygulamaları, standart e-ticaret siteleri, kurumsal CRM ve ERP sistemleri ile bölgesel düzeyde çalışan mikroservis mimarileri için tercih edilir23.

#### **5\. Ekosistem Entegrasyonu**

Compute Engine, GKE, Cloud Run, App Engine, BigQuery, Cloud Storage ve Cloud IAM ile tam uyumludur12.

### **AlloyDB for PostgreSQL**

#### **1\. Ne Nedir?**

AlloyDB for PostgreSQL, Google Cloud'un en zorlu kurumsal iş yükleri için özel olarak geliştirdiği, standart PostgreSQL ile tam uyumlu, hesaplama ve depolama katmanları birbirinden ayrılmış yeni nesil yüksek performanslı ilişkisel veritabanı hizmetidir11.

#### **2\. Ne İşe Yarar?**

Geleneksel PostgreSQL mimarisinin disk girdi/çıktı (I/O) darboğazları ve büyük ölçekli analitik sorgulardaki yavaşlık problemlerini çözer. Google'ın tescilli dağıtık depolama katmanı sayesinde standart PostgreSQL'e göre işlemsel iş yüklerinde 4 kat, analitik sorgularda ise entegre kolon tabanlı motoru (columnar engine) sayesinde 100 kata kadar daha hızlı performans sunar11.

#### **3\. Nasıl Kullanılır?**

Uygulamalar standart PostgreSQL sürücüleriyle hiçbir kod değişikliği yapmadan AlloyDB kümesine bağlanır11. Girdi olarak ilişkisel veri yazma/okuma talepleri ve ağır analitik sorgular alınır. AlloyDB, gelen veriyi paylaşılan depolama katmanına yazar; okuma isteklerini ise akıllı bellek önbelleği ve otomatik kolonlaştırma mekanizmasıyla işleyerek milisaniyeler mertebesinde çıktı üretir11.

#### **4\. Tipik Kullanım Senaryoları**

Eski ticari veritabanlarından (Oracle, SQL Server) açık kaynaklı PostgreSQL dünyasına yüksek performans gereksinimiyle geçiş senaryoları, hem yoğun işlem hem de gerçek zamanlı analitik gerektiren finansal uygulamalar ile yapay zeka entegrasyonlu modern projeler için en uygun seçenektir11.

#### **5\. Ekosistem Entegrasyonu**

Vertex AI, Cloud Run, GKE, BigQuery, Datastream ve Cloud Storage ile entegre çalışır11.

### **Cloud Bigtable**

#### **1\. Ne Nedir?**

Cloud Bigtable, Google'ın arama, haritalar ve finans gibi milyarlarca kullanıcısı olan kendi servislerinde de kullandığı, ultra düşük gecikmeli ve terabaytlardan petabaytlara kadar kesintisiz ölçeklenen geniş sütunlu NoSQL veritabanı hizmetidir28.

#### **2\. Ne İşe Yarar?**

Milyarlarca satır ve sütundan oluşan devasa veri kümelerinde, ilişkisel veritabanlarının indeksleme yetersizlikleri ve yüksek yazma yoğunluğu altındaki kilitlenme problemlerini çözer. Yatayda doğrusal olarak ölçeklenerek, sisteme eklenen her düğümle birlikte yazma/okuma kapasitesini kesintisiz artırma avantajı sunar.

#### **3\. Nasıl Kullanılır?**

Veriler tek bir indeks olan satır anahtarı (row key) temelinde sıralı olarak saklanır. Girdi olarak IoT cihazlarından gelen anlık telemetri verileri veya kullanıcı tıklama verileri yüksek hızda akıtılır. Bigtable, veriyi bellek içi ve disk üzerindeki optimize edilmiş tablolarda düzenler; çıktıyı satır anahtarı üzerinden yapılan nokta atışı sorgularıyla milisaniyeler içinde sunar.

#### **4\. Tipik Kullanım Senaryoları**

Yüksek hacimli IoT telemetri verisi toplama ve işleme, reklam teknolojilerinde anlık kullanıcı profilleme, finansal piyasaların zaman serisi veri analitiği ve yapay zeka modelleri için özellik saklama deposu (feature store) oluşturma durumlarında tercih edilmelidir.

#### **5\. Ekosistem Entegrasyonu**

Dataflow, Dataproc, BigQuery, Cloud IAM ve GKE ile entegre çalışır.

### **Memorystore (Redis/Memcached)**

#### **1\. Ne Nedir?**

Memorystore; açık kaynaklı Redis ve Memcached bellek içi veri depolarıyla tam uyumlu çalışan, mikro saniyeler düzeyinde erişim süresi sunan tamamen yönetilen bir önbellekleme ve geçici veri depolama servisidir4.

#### **2\. Ne İşe Yarar?**

Disk tabanlı veritabanlarına sürekli erişim yapılmasının yarattığı gecikme darboğazlarını ve veritabanı üzerindeki aşırı yükü çözer. Sık erişilen verileri bellekte tutarak uygulama yanıt sürelerini radikal biçimde düşürür ve yüksek trafik dalgalanmalarını sönümler.

#### **3\. Nasıl Kullanılır?**

Uygulama, ana veritabanına sorgu atmadan önce Memorystore'a sorgu atar (girdi). Veri Memorystore'da mevcutsa doğrudan bellekten döndürülür (çıktı). Eğer mevcut değilse, veri ana tabandan okunup Memorystore'ya yazılır. Sistem, verilerin bellekte tutulma süresini (TTL) otomatik olarak yönetir.

#### **4\. Tipik Kullanım Senaryoları**

Web ve mobil uygulamaların oturum yönetimi (session store), yapay zeka ajanlarının kısa vadeli sohbet bellekleri, sık sorgulanan SQL sonuçlarının önbelleğe alınması ve canlı liderlik tablolarının yönetilmesi senaryolarında tercih edilmelidir4.

#### **5\. Ekosistem Entegrasyonu**

App Engine, Compute Engine, GKE, Cloud Run, Cloud Run Functions ve Cloud SQL/AlloyDB ile doğrudan entegre çalışır.

## **4\. Veri Analitiği, Büyük Veri ve Gerçek Zamanlı Veri Akışı (Data Analytics, Big Data & Streaming)**

### **BigQuery**

#### **1\. Ne Nedir?**

BigQuery, sunucusuz, yüksek düzeyde ölçeklenebilir ve çoklu bulut yeteneklerine sahip, petabaytlarca veri üzerinde SQL sorguları ile saniyeler içinde analiz yapabilen kurumsal veri ambarı ve analitik platformudur1.

#### **2\. Ne İşe Yarar?**

Geleneksel veri ambarlarının yüksek kurulum maliyetleri, kapasite sınırları ve yavaş sorgu süreleri problemlerini çözer. Depolama ve hesaplama katmanlarını birbirinden bağımsız ölçeklendirerek, kullanıcılara altyapı yönetimi olmaksızın sadece çalıştırılan SQL sorgularında taranan veri miktarı üzerinden ödeme yapma esnekliği sunar.

#### **3\. Nasıl Kullanılır?**

Yapılandırılmış veya yarı yapılandırılmış veriler toplu ya da akış halinde BigQuery tablolarına aktarılır (girdi). Kullanıcılar web konsolu veya API üzerinden standart ANSI-SQL dilini kullanarak sorgular çalıştırır. BigQuery, sorguyu binlerce paralel işlemciye dağıtarak milisaniyeler içinde analitik sonuçlar (çıktı) üretir. Dahili makine öğrenmesi özellikleri sayesinde SQL sorguları ile doğrudan model eğitimi gerçekleştirilebilir.

#### **4\. Tipik Kullanım Senaryoları**

Şirket genelindeki tüm veri kaynaklarının tek bir yerde toplanarak analiz edilmesi, büyük veri üzerinde anlık analitik sorguların çalıştırılması ve gerçek zamanlı iş zekası raporlaması için ana platform olarak konumlandırılmalıdır.

#### **5\. Ekosistem Entegrasyonu**

Looker, Cloud Storage, Dataflow, Dataproc, Vertex AI, Pub/Sub ve Datastream ile doğrudan konuşur3.

### **Dataproc**

#### **1\. Ne Nedir?**

Dataproc; Apache Spark, Apache Hadoop, Presto ve Flink gibi açık kaynaklı büyük veri işleme çerçevelerini Google Cloud üzerinde çalıştıran, tamamen yönetilen ve hızlı ölçeklenebilir bir küme servisidir.

#### **2\. Ne İşe Yarar?**

Şirket içi Hadoop ve Spark kümelerini kurmanın, donanım satın almanın ve bu altyapıyı ayakta tutmanın getirdiği yüksek maliyet ve operasyonel zorlukları ortadan kaldırır. Küme oluşturma süresini 90 saniyenin altına indirerek dinamik ölçeklenebilirlik ve iş bitiminde kümeyi yok ederek yüksek maliyet tasarrufu sağlar.

#### **3\. Nasıl Kullanılır?**

Geliştiriciler istedikleri Spark/Hadoop konfigürasyonuna sahip bir Dataproc kümesi başlatır. Girdi olarak Cloud Storage veya BigQuery üzerinde depolanan veri dosyaları hedef alınır. Spark veya MapReduce işleri küme üzerinde paralel olarak koordine edilir. Çıktı veri kümeleri dönüştürülmüş olarak tekrar Cloud Storage veya BigQuery'ye yazılır.

#### **4\. Tipik Kullanım Senaryoları**

Mevcut şirket içi Apache Spark/Hadoop iş yüklerinin kod değişikliğiyle uğraşmadan buluta taşınması ve büyük veri kümeleri üzerinde toplu veri dönüşüm (ETL) işlemleri için tercih edilir.

#### **5\. Ekosistem Entegrasyonu**

Cloud Storage, BigQuery, Vertex AI Workbench, Cloud IAM ve Compute Engine ile entegre çalışır.

### **Dataflow**

#### **1\. Ne Nedir?**

Dataflow, Apache Beam programlama modeline dayanan, hem toplu hem de gerçek zamanlı akan verileri aynı anda, yüksek performanslı ve tutarlı bir şekilde işleyebilen, tamamen yönetilen ve sunucusuz bir veri işleme hizmetidir12.

#### **2\. Ne İşe Yarar?**

Akan veri hatlarında karşılaşılan veri gecikmesi, eksik veri yönetimi ve işleme kapasitesinin anlık veri dalgalanmalarına göre dinamik olarak ölçeklenememesi problemlerini çözer. Otomatik işçi ölçekleme mekanizması ve tam bir kez (exactly-once) işleme garantisi sunar.

#### **3\. Nasıl Kullanılır?**

Geliştirici Apache Beam SDK kullanarak bir veri işleme boru hattı yazar. Bu boru hattı Dataflow üzerinde çalıştırılır. Girdi olarak Pub/Sub'dan akan canlı mesajlar veya Cloud Storage'daki dosyalar alınır12. Dataflow verileri dilimler halinde işler, dönüştürür ve çıktı olarak BigQuery veya Cloud Bigtable gibi hedef sistemlere yazar12.

#### **4\. Tipik Kullanım Senaryoları**

Canlı dolandırıcılık tespiti (fraud detection) sistemleri, anlık finansal işlem analizleri, IoT cihazlarından gelen verilerin anlık filtrelenmesi ve dönüştürülmesi süreçlerinde tercih edilmelidir.

#### **5\. Ekosistem Entegrasyonu**

Pub/Sub, BigQuery, Cloud Storage, Cloud Bigtable ve Cloud IAM ile derin entegrasyona sahiptir12.

### **Pub/Sub**

#### **1\. Ne Nedir?**

Pub/Sub, asenkron mikroservis mimarileri ve gerçek zamanlı veri analitiği hatları arasında mesaj iletimini sağlayan, küresel ölçekte çalışan, sunucusuz ve son derece dayanıklı bir mesaj kuyruğu ve olay veri akışı servisidir16.

#### **2\. Ne İşe Yarar?**

Sistemlerin birbirine sıkı sıkıya bağlı olması durumunda ortaya çıkan, bir servisteki arızanın tüm sistemi kilitlemesi problemini çözer. Gönderici ve alıcı sistemleri birbirinden tamamen bağımsızlaştırarak, yüksek trafik dalgalanmalarını sönümler ve mesajların kaybolmadan güvenli bir şekilde iletilmesini garanti eder.

#### **3\. Nasıl Kullanılır?**

Gönderici sistemler belirli bir konuya (Topic) mesajlar yayınlar. Mesajlar Pub/Sub katmanında depolanır. Alıcı sistemler bu konuya bağlı abonelikler (Subscriptions) üzerinden mesajları çeker veya Pub/Sub mesajları alıcılara otomatik olarak gönderir20. Mesaj başarıyla alındığında bir onay gönderilir ve süreç tamamlanır.

#### **4\. Tipik Kullanım Senaryoları**

Mikroservisler arası asenkron olay tabanlı iletişim, sistem günlüklerinin merkezi olarak toplanması ve IoT telemetri verilerinin sisteme giriş noktası olarak konumlandırılması durumlarında tercih edilir16.

#### **5\. Ekosistem Entegrasyonu**

Cloud Run, Cloud Run Functions, Dataflow, BigQuery, Cloud Storage ve Eventarc ile kesintisiz entegre çalışır16.

### **Data Fusion**

#### **1\. Ne Nedir?**

Data Fusion, kod yazmadan görsel bir arayüz üzerinden veri entegrasyonu (ETL/ELT) boru hatları oluşturulmasını sağlayan, açık kaynaklı CDAP tabanlı, tamamen yönetilen bir bulut servisidir.

#### **2\. Ne İşe Yarar?**

Veri mühendislerinin ve iş analistlerinin, farklı sistemlerden gelen verileri birleştirmek için karmaşık kod yazma zorunluluğunu ortadan kaldırır. Hazır konnektör ve dönüşüm kütüphanesi sayesinde veri entegrasyon süreçlerini standartlaştırır ve hızlandırır.

#### **3\. Nasıl Kullanılır?**

Kullanıcılar sürükle-bırak yöntemiyle çalışan stüdyo arayüzünü kullanarak kaynak sistemleri, veri dönüşüm adımlarını ve hedef sistemleri bağlayan bir akış şeması tasarlar. Data Fusion arka planda bu görsel akışı optimize edilmiş bir Dataproc işine dönüştürerek çalıştırır ve çıktı olarak dönüştürülmüş veriyi hedef sistemlere yazar.

#### **4\. Tipik Kullanım Senaryoları**

Şirket içi ana bilgisayarlar (mainframe), SAP ve ilişkisel veritabanı verilerinin BigQuery'ye kodsuz taşınması ile kurumsal veri gölü oluşturma süreçlerinde kullanılmalıdır.

#### **5\. Ekosistem Entegrasyonu**

Cloud Storage, BigQuery, Dataproc, Cloud Spanner, Cloud SQL ve Cloud IAM ile doğrudan entegredir.

### **Datastream**

#### **1\. Ne Nedir?**

Datastream; Oracle, MySQL, PostgreSQL ve SQL Server gibi ilişkisel kaynaklardan BigQuery, Cloud Storage ve Spanner gibi hedef sistemlere gerçek zamanlı ve minimum gecikmeyle veri replikasyonu sağlayan sunucusuz bir Değişen Veri Yakalama (Change Data Capture \- CDC) servisidir.

#### **2\. Ne İşe Yarar?**

Operasyonel veritabanlarındaki güncellemelerin analitik sistemlere aktarılması sırasında oluşan gecikmeleri ve kaynak veritabanına binen sorgu yükünü çözer. Kaynak veritabanlarının işlem günlüklerini doğrudan okuyarak, sistem performansını etkilemeden saniyeler içinde değişiklikleri yakalar ve kopyalar.

#### **3\. Nasıl Kullanılır?**

Girdi olarak hedef kaynak veritabanının bağlantı bilgileri ve izlenecek tablolar belirlenir. Datastream, CDC protokollerini kullanarak kaynaktaki her ekleme, güncelleme ve silme işlemini anında yakalar. Bu değişiklikleri akış halinde işleyerek çıktı hedefinde (örn. Cloud Storage veya doğrudan BigQuery) güncel verileri oluşturur.

#### **4\. Tipik Kullanım Senaryoları**

Canlı veri analitiği için operasyonel veritabanlarından BigQuery'ye sıfır gecikmeli veri replikasyonu ve minimum kesinti süresiyle veritabanı göçü süreçleri için idealdir.

#### **5\. Ekosistem Entegrasyonu**

Cloud Storage, BigQuery, Cloud SQL, AlloyDB ve Cloud Spanner ile doğrudan entegrasyonu mevcuttur17.

## **5\. Ağ Teknolojileri, Güvenlik ve Kimlik Yönetimi (Networking, Security & Identity)**

### **Cloud Load Balancing**

#### **1\. Ne Nedir?**

Cloud Load Balancing, Google'ın dünya genelindeki yüksek hızlı fiber optik omurga ağı üzerinde çalışan, tek bir IP adresi üzerinden gelen küresel ağ trafiğini arka uçtaki sistemlere milisaniyeler düzeyinde dağıtan, yazılım tabanlı ve tamamen yönetilen bir yük dengeleme hizmetidir.

#### **2\. Ne İşe Yarar?**

Geleneksel donanım tabanlı yük dengeleyicilerin fiziksel sınırları ve tek bir bölgedeki çökmelerin tüm sistemi durdurması problemlerini çözer. Kullanıcıya en yakın Google sınır yönlendiricisinde trafiği karşılayarak hızlı güvenli bağlantı sonlandırması sağlar ve dünya genelinde kesintisiz yüksek kullanılabilirlik sunar.

#### **3\. Nasıl Kullanılır?**

Girdi olarak kullanıcılardan gelen ağ istekleri alınır. Yük dengeleyici, yapılandırılmış yönlendirme kurallarını analiz eder. Sağlık kontrolü (health check) mekanizması ile canlı olduğu doğrulanan en uygun arka uç sunucu grubuna trafiği yönlendirerek çıktıyı kullanıcıya ulaştırır.

#### **4\. Tipik Kullanım Senaryoları**

Küresel çapta hizmet veren ve yüksek kullanılabilirlik gerektiren web siteleri, ani trafik patlamaları yaşayan mobil arka plan servisleri ve çoklu bölgede yedekli çalışan sistem mimarileri için tercih edilir20.

#### **5\. Ekosistem Entegrasyonu**

Google Cloud Armor, VPC, Compute Engine, GKE, Cloud Run ve Cloud DNS ile doğrudan entegre çalışır20.

### **Google Cloud Armor**

#### **1\. Ne Nedir?**

Google Cloud Armor, web uygulamalarını ve API'leri dağıtık hizmet dışı bırakma (DDoS) saldırılarına, OWASP Top 10 açıklarına ve kötü niyetli internet trafiğine karşı Google'ın küresel altyapısı seviyesinde koruyan gelişmiş bir Web Uygulaması Güvenlik Duvarı (WAF) hizmetidir.

#### **2\. Ne İşe Yarar?**

Kötü niyetli botların ve siber saldırıların uygulama sunucularına ulaşarak sistemi çökertmesi veya veri sızdırması problemini çözer. Saldırıları daha uygulama sunucusuna ulaşmadan, Google'ın ağ sınırında engellediği için sunucu kaynaklarının gereksiz yere tüketilmesini önler.

#### **3\. Nasıl Kullanılır?**

Güvenlik politikaları oluşturulur ve yük dengeleyici ön uçlarına bağlanır. Girdi, gelen internet trafiğidir. Cloud Armor; IP adresleri, coğrafi konumlar ve istek başlıkları gibi parametreleri analiz eder. Tehdit içeren istekleri engeller; güvenli isteklerin ise arkadaki sunuculara geçmesine izin vererek çıktıyı oluşturur.

#### **4\. Tipik Kullanım Senaryoları**

Finans ve e-ticaret sitelerinin bot saldırılarına karşı korunması, genel erişime açık web sitelerinin DDoS saldırılarına karşı güvenliğinin sağlanması ve OWASP Top 10 açıklarına karşı hızlı sanal yama yapılması durumlarında tercih edilmelidir.

#### **5\. Ekosistem Entegrasyonu**

Cloud Load Balancing, VPC ve Chronicle Security ile derin entegrasyona sahiptir22.

### **Virtual Private Cloud (VPC)**

#### **1\. Ne Nedir?**

VPC, Google Cloud üzerinde çalışan bulut kaynakları için mantıksal olarak izole edilmiş, tamamen yazılım tanımlı ve küresel ölçekte çalışan özel sanal ağ altyapısıdır12.

#### **2\. Ne İşe Yarar?**

Buluttaki kaynakların internete doğrudan açık olması durumunda ortaya çıkacak güvenlik açıklarını çözer. Google VPC'si küresel bir yapıya sahiptir; yani tek bir VPC içindeki farklı bölgelerde yer alan alt ağlar, birbirleriyle internete çıkmadan, Google'ın özel iç ağı üzerinden doğrudan ve güvenli bir şekilde konuşabilirler.

#### **3\. Nasıl Kullanılır?**

Kullanıcılar bir VPC oluşturur ve içinde farklı bölgeler için IP aralıkları belirleyerek alt ağlar tanımlar. Güvenlik duvarı kuralları ve rotalar belirlenir22. Girdi, kaynakların birbirine veya dış dünyaya gönderdiği ağ paketleridir. VPC, bu paketleri tanımlanan rotalar veya VPN bağlantıları üzerinden hedeflerine güvenli bir şekilde yönlendirerek çıktıyı sunar12.

#### **4\. Tipik Kullanım Senaryoları**

Şirket içi veri merkezlerinin buluta güvenli bir şekilde bağlanması (Hibrit Bulut) ve çok katmanlı kurumsal uygulamaların ağ seviyesinde birbirinden izole edilmesi durumlarında kullanılmalıdır12.

#### **5\. Ekosistem Entegrasyonu**

Compute Engine, GKE, Cloud SQL, AlloyDB, Cloud Load Balancing ve Secret Manager gibi neredeyse tüm GCP servisleriyle entegredir12.

### **Secret Manager**

#### **1\. Ne Nedir?**

Secret Manager; API anahtarları, şifreler, sertifikalar ve veri tabanı bağlantı dizgeleri gibi hassas kurumsal verilerin merkezi, güvenli ve şifrelenmiş olarak depolanmasını, yönetilmesini ve denetlenmesini sağlayan bulut hizmetidir.

#### **2\. Ne İşe Yarar?**

Geliştiricilerin hassas şifreleri uygulama kodlarının içine yazmasıyla oluşan güvenlik riskini ortadan kaldırır. Sırların yaşam döngüsünü (rotasyon, iptal) merkezi olarak yönetmeyi sağlar ve erişim kayıtlarını denetler.

#### **3\. Nasıl Kullanılır?**

Yönetici, Secret Manager üzerinde bir sır tanımı yapar ve hassas veriyi girdi olarak buraya yükler. Veri, AES-256 standardında şifrelenerek saklanır. Uygulamalar çalışma zamanında Cloud IAM yetkilendirmesiyle Secret Manager API'sini çağırır. Sistem, kimlik doğrulamasının ardından sadece yetkili uygulamaya sırrın ham değerini çıktı olarak teslim eder.

#### **4\. Tipik Kullanım Senaryoları**

Mikroservislerin veritabanı şifrelerine güvenli erişimi, harici API anahtarlarının saklanması ve TLS/SSL sertifikalarının otomatik rotasyon süreçlerinde tercih edilmelidir.

#### **5\. Ekosistem Entegrasyonu**

Cloud IAM, Cloud Run, Cloud Run Functions, GKE ve Cloud Build ile doğrudan entegre çalışır.

### **Cloud IAM**

#### **1\. Ne Nedir?**

Cloud IAM, Google Cloud üzerindeki kaynaklara kimlerin, hangi düzeyde erişebileceğini belirleyen ve yöneten merkezi kimlik ve erişim yönetimi sistemidir30.

#### **2\. Ne İşe Yarar?**

En az ayrıcalık ilkesi çerçevesinde, sistem kaynaklarına gereğinden fazla yetki verilmesinin yarattığı güvenlik açıklarını çözer. Rol tabanlı erişim kontrolü (RBAC) sunarak, insan hatalarından veya yetki suistimallerinden kaynaklı veri sızıntılarını engeller.

#### **3\. Nasıl Kullanılır?**

Sistemde kimlik (üye/servis hesabı), rol ve politika bileşenleri yer alır30. Girdi olarak bir kullanıcının bir GCP kaynağı üzerinde işlem yapma talebi alınır. IAM politikası değerlendirilir; kimlik doğrulanırsa ve rolü uygunsa işleme onay verilir (çıktı), aksi halde talep reddedilir.

#### **4\. Tipik Kullanım Senaryoları**

Geliştiricilere sadece test ortamlarında düzenleme, üretim ortamlarında ise sadece görüntüleme yetkisi tanımlanması ve uygulamaların insan müdahalesi olmadan çalışabilmesi için servis hesaplarının yetkilendirilmesi durumlarında kullanılır.

#### **5\. Ekosistem Entegrasyonu**

GCP ekosistemindeki tüm servisler güvenlik ve yetkilendirme katmanı olarak Cloud IAM ile entegre çalışmak zorundadır3.

### **Chronicle Security ve Mandiant Çözümleri**

#### **1\. Ne Nedir?**

Chronicle Security (Google Security Operations) ve Mandiant Solutions, kurumsal tehdit tespiti, olay müdahalesi ve siber tehdit istihbaratı sunan, Google'ın büyük veri analiz gücüyle entegre edilmiş ileri düzey siber güvenlik operasyonları ekosistemidir22.

#### **2\. Ne İşe Yarar?**

Geleneksel güvenlik analizi (SIEM) çözümlerinin petabaytlarca logu analiz etmedeki yavaşlığı problemlerini çözer22. Mandiant'ın küresel siber tehdit istihbaratı gücü ile Google'ın arama hızı düzeyindeki veri analiz yeteneğini birleştirerek, kurumsal ağlardaki gizli siber tehditleri saniyeler içinde tespit eder ve otomatik olarak yanıtlar22.

#### **3\. Nasıl Kullanılır?**

Girdi olarak kurumsal sunuculardan, güvenlik duvarlarından ve bulut servislerinden gelen log verileri Chronicle platformuna akar22. Chronicle, bu logları ortak bir veri modelinde standartlaştırır. Mandiant Threat Intelligence verileriyle loglar harmanlanır ve sistem tehdit tespiti yaptığında çıktı olarak güvenlik analistlerine önceliklendirilmiş alarm ve otomatik müdahale planları üretir22.

#### **4\. Tipik Kullanım Senaryoları**

Kurumsal düzeyde tüm IT altyapısının güvenlik olaylarının tek bir merkezden izlenmesi (SOC) ve siber saldırı anında otomatik karantina senaryolarının işletilmesi durumlarında tercih edilir22.

#### **5\. Ekosistem Entegrasyonu**

VPC Flow Logs, Google Cloud Armor, Cloud IAM, Cloud Audit Logs ve Google Workspace ile tam entegredir22.

## **6\. Depolama ve DevOps Çözümleri (Storage & DevOps)**

### **Cloud Storage (GCS)**

#### **1\. Ne Nedir?**

Cloud Storage, dünya genelinde yüksek kullanılabilirlik, yüksek dayanıklılık ve sınırsız kapasite sunan, yapılandırılmamış veriler için tasarlanmış tamamen yönetilen nesne depolama (object storage) servisidir6.

#### **2\. Ne İşe Yarar?**

Veri boyutunun büyümesiyle birlikte fiziksel disk yönetimi ve yedekleme zorluklarını çözer. Verileri erişim sıklığına göre Standard, Nearline, Coldline ve Archive olmak üzere farklı sınıflarda depolama imkanı sunarak kurumsal maliyetleri optimize eder.

#### **3\. Nasıl Kullanılır?**

Kullanıcılar Bucket adı verilen depolama alanları oluşturur. Girdi olarak herhangi bir formattaki dosyalar (görseller, yedekler, loglar) sisteme yüklenir6. Cloud Storage, her dosyayı bir nesne olarak meta verileriyle birlikte saklar. Çıktı olarak HTTP/HTTPS protokolleri üzerinden dosyalara hızlıca erişim sağlanır.

#### **4\. Tipik Kullanım Senaryoları**

Web sitelerinin statik dosyalarının barındırılması, veritabanı yedeklerinin uzun vadeli saklanması ve büyük veri analizleri için ham veri gölü (data lake) altyapısının kurulması durumlarında tercih edilmelidir4.

#### **5\. Ekosistem Entegrasyonu**

Compute Engine, GKE, Cloud Run, BigQuery, Dataflow, Dataproc ve Vertex AI ile doğrudan entegredir4.

### **Filestore**

#### **1\. Ne Nedir?**

Filestore, Google Cloud üzerinde çalışan uygulamalar için yüksek performanslı, tamamen yönetilen ve NFS protokollerini destekleyen ağa bağlı dosya depolama (NAS) servisidir.

#### **2\. Ne İşe Yarar?**

Aynı anda yüzlerce sanal makine veya konteynerin, ortak bir dosya sistemine son derece düşük gecikme ve yüksek IOPS hızlarıyla erişerek veri yazma ve okuma yapamaması problemini çözer. POSIX uyumlu yapısı sayesinde mevcut uygulamaların kod değişikliği yapılmadan buluta taşınmasını sağlar.

#### **3\. Nasıl Kullanılır?**

GCP konsolunda bir Filestore örneği oluşturulur ve kapasite belirlenir. Girdi, sanal makineler veya GKE podları tarafından yapılan NFS mount (bağlama) talepleridir. Filestore, bu sunuculara ortak bir disk alanı sunar; çıktı olarak tüm istemciler ortak dosya sistemindeki dosyalara eşzamanlı olarak erişebilir.

#### **4\. Tipik Kullanım Senaryoları**

Çok sayıda web sunucusunun ortak bir dosya dizinini paylaştığı içerik yönetim sistemleri ve medya/video işleme çiftlikleri için en uygun çözümdür.

#### **5\. Ekosistem Entegrasyonu**

Compute Engine, GKE, VPC ve Cloud Monitoring ile doğrudan konuşur.

### **Cloud Build**

#### **1\. Ne Nedir?**

Cloud Build, Google Cloud'un sunduğu, kodun derlenmesi, test edilmesi, paketlenmesi ve güvenli bir şekilde dağıtılmasını sağlayan tamamen sunucusuz ve yüksek düzeyde ölçeklenebilir bir sürekli entegrasyon ve sürekli dağıtım (CI/CD) platformudur.

#### **2\. Ne İşe Yarar?**

CI/CD süreçleri için özel sunucuların kurulması ve bu sunucuların atıl kaldığı zamanlarda oluşan maliyet kayıplarını önler. Sunucusuz yapısı sayesinde, derleme talebi geldiğinde saniyeler içinde paralel işçiler ayağa kalkar ve iş bitiminde kapanarak sadece çalışma süresi bazında ücretlendirilir.

#### **3\. Nasıl Kullanılır?**

Geliştirici, derleme adımlarını tanımlayan bir yapılandırma dosyası hazırlar. Girdi, bir Git deposundaki kod değişiklikleridir. Cloud Build, tanımlanan adımları güvenli konteynerler içinde çalıştırır. Çıktı olarak derlenmiş kod dosyaları veya Artifact Registry'ye yüklenmiş konteyner imajları üretilir20.

#### **4\. Tipik Kullanım Senaryoları**

Uygulama kodlarının her güncelleme sonrasında otomatik olarak test edilmesi, Docker konteyner imajlarının otomatik üretilip güvenlik taramasından geçirilmesi ve bulut ortamlarına kodun otomatik olarak dağıtılması süreçlerinde kullanılır20.

#### **5\. Ekosistem Entegrasyonu**

Artifact Registry, Cloud Run, GKE, Cloud Storage ve Secret Manager ile entegre çalışır17.

### **Artifact Registry**

#### **1\. Ne Nedir?**

Artifact Registry, kurumsal yazılım geliştirme süreçlerinde kullanılan konteyner imajları ve dil paketlerinin güvenli, merkezi ve tamamen yönetilen bir biçimde depolanmasını sağlayan paket yönetim servisidir.

#### **2\. Ne İşe Yarar?**

Sadece Docker imajlarını değil, kurumsal düzeyde tüm uygulama paketlerini (npm, maven, pip) tek bir çatı altında yönetme ihtiyacını karşılar. Paketlerin güvenlik açıklarına karşı otomatik olarak taranmasını sağlar ve yazılım tedarik zinciri güvenliğini destekler22.

#### **3\. Nasıl Kullanılır?**

Girdi olarak geliştirme araçları kullanılarak sisteme paketler yüklenir. Artifact Registry, paketi depolar ve arka planda otomatik güvenlik taraması gerçekleştirir. Uygulamalar veya Kubernetes gibi çalışma zamanları, ihtiyaç duyduklarında bu paketleri çekerek çıktı olarak uygulamalarını ayağa kaldırır20.

#### **4\. Tipik Kullanım Senaryoları**

Docker konteyner imajlarının sürüm kontrolü altında güvenli şekilde saklanması ve şirket içinde paylaşılan özel kütüphanelerin merkezi olarak depolanması durumlarında tercih edilir20.

#### **5\. Ekosistem Entegrasyonu**

Cloud Build, GKE, Cloud Run, Compute Engine ve Cloud IAM ile doğrudan entegredir20.

### **Cloud Scheduler**

#### **1\. Ne Nedir?**

Cloud Scheduler, Google Cloud Platform üzerinde zamanlanmış görevlerin kurumsal düzeyde, yüksek kullanılabilirlikle ve tamamen yönetilen bir şekilde çalıştırılmasını sağlayan sunucusuz bir bulut kronometresidir20.

#### **2\. Ne İşe Yarar?**

Geleneksel işletim sistemlerindeki zamanlanmış görev yapılarının sunucu çöktüğünde çalışmaması ve yedeklilik sunmaması problemlerini çözer. Görevlerin her koşulda çalışmasını garanti eder.

#### **3\. Nasıl Kullanılır?**

Kullanıcı, standart cron formatında bir zamanlama kuralı belirler. Girdi olarak tetiklenecek hedef belirlenir; bu bir HTTP uç noktası veya bir Pub/Sub konusu olabilir20. Zamanı geldiğinde Cloud Scheduler hedefi tetikler ve çıktı olarak ilgili servise bir çağrı göndererek asenkron bir sürecin başlamasını sağlar20.

#### **4\. Tipik Kullanım Senaryoları**

Veri tabanı yedekleme işlemlerinin otomatik başlatılması, her ayın sonunda otomatik fatura kesilmesi için bir mikroservisin tetiklenmesi ve günlük sistem raporlarının oluşturulması senaryolarında kullanılmalıdır20.

#### **5\. Ekosistem Entegrasyonu**

Pub/Sub, Cloud Run, Cloud Run Functions ve App Engine ile doğrudan entegrasyona sahiptir20.

## **7\. GCP İle Bağlantılı / Entegre Google Ekosistem Çözümleri**

### **Firebase Platformu (Authentication, Realtime DB, Crashlytics, Hosting)**

#### **1\. Ne Nedir?**

Firebase, Google'ın mobil ve web uygulama geliştiricileri için sunduğu, istemci odaklı çalışarak arka uç geliştirme yükünü en aza indiren, bünyesinde Authentication, Realtime DB, Crashlytics ve Hosting gibi popüler alt bileşenleri barındıran entegre uygulama geliştirme platformudur6.

#### **2\. Ne İşe Yarar?**

Yazılım ekiplerinin her mobil veya web projesi için sıfırdan kullanıcı kimlik doğrulama, anlık veri senkronizasyonu, hata izleme ve güvenli barındırma (hosting) altyapısı tasarlama zorunluluğunu ortadan kaldırır. GCP'nin kurumsal gücünü geliştirici dostu tek bir SDK altında sunarak ürün geliştirme süreçlerini hızlandırır16.

#### **3\. Nasıl Kullanılır?**

Uygulamalara Firebase istemci SDK'ları entegre edilir. Authentication alt bileşeniyle kullanıcı girişleri yönetilir (girdi). Realtime DB ile veriler JSON ağacında saklanır ve istemcilere gerçek zamanlı senkronize edilir. Crashlytics, uygulamadaki çökmeleri otomatik izleyip raporlar. Hosting ise statik web varlıklarını Google'ın CDN ağı üzerinden küresel olarak dağıtır (çıktı).

#### **4\. Tipik Kullanım Senaryoları**

Hızla pazara sürülmesi gereken mobil sosyal ağlar, işbirlikçi sohbet uygulamaları, gerçek zamanlı veri takibi gerektiren gösterge panelleri ve kullanıcı davranışı analitiği içeren projeler için tercih edilmelidir16.

#### **5\. Ekosistem Entegrasyonu**

Cloud Run Functions, Cloud Firestore, Cloud Storage ve BigQuery ile kesintisiz veri aktarımı ve tetikleme mekanizmaları üzerinden çalışır16.

### **Looker ve Looker Studio**

#### **1\. Ne Nedir?**

Looker ve Looker Studio, işletmelerin karmaşık verilerini anlamlı görsel raporlara, grafiklere ve interaktif kontrol panellerine dönüştürerek veri odaklı karar almalarını sağlayan iş zekası (BI) ve veri analitiği çözümleridir12.

#### **2\. Ne İşe Yarar?**

Şirket genelindeki dağınık veri kaynaklarının tek bir noktadan analiz edilmesini sağlayarak bilgi silolarını yıkar. Looker, LookML anlamsal modelleme dili ile tüm kurum genelinde "tek bir doğru veri tanımı" (single source of truth) oluşturulmasına imkan tanır.

#### **3\. Nasıl Kullanılır?**

Kullanıcılar veritabanı veya veri ambarı bağlantılarını sisteme tanımlarlar (girdi). Looker Studio üzerinde sürükle-bırak yöntemleri ile interaktif görsel paneller tasarlanır. Arka planda Looker, kullanıcıların görsel taleplerini doğrudan hedef veritabanının anlayacağı optimize edilmiş SQL sorgularına dönüştürür ve çıktı olarak canlı veriyi ekranlara yansıtır.

#### **4\. Tipik Kullanım Senaryoları**

Şirket üst yönetimi için anlık KPI ve finansal raporlama ekranlarının hazırlanması, pazarlama departmanlarının kampanya performans analizleri ve operasyonel verimlilik takipleri için kullanılır.

#### **5\. Ekosistem Entegrasyonu**

BigQuery, Cloud SQL, AlloyDB, Cloud Spanner, Cloud Storage ve Google Sheets ile doğrudan yerleşik entegrasyona sahiptir12.

### **Apigee API Management**

#### **1\. Ne Nedir?**

Apigee, kurumsal API'lerin (Application Programming Interface) tasarlanması, güvence altına alınması, analiz edilmesi, kota sınırlarının yönetilmesi ve ölçeklenmesi süreçlerini merkezi olarak üstlenen lider bir API yönetim platformudur4.

#### **2\. Ne İşe Yarar?**

Arka uç servislerinin dış dünyaya açılması esnasında karşılaşılan güvenlik açıkları, kontrolsüz trafik yükleri ve servis izleme zorluklarını çözer. Yapay zeka ajanlarının veya harici üçüncü taraf entegrasyonlarının kurumsal sistemlerle kontrollü ve güvenli konuşmasını sağlar4.

#### **3\. Nasıl Kullanılır?**

Uygulamalardan gelen tüm API istekleri (girdi) öncelikli olarak Apigee Gateway katmanında karşılanır4. Sistem, API anahtarlarını doğrular, yetki kontrollerini yapar, trafik sınırlama kurallarını uygular ve talebi arka plandaki mikroservise iletir. Servisten dönen yanıtı optimize ederek istemciye çıktı olarak teslim eder.

#### **4\. Tipik Kullanım Senaryoları**

Finansal kuruluşların açık bankacılık API'lerini dış geliştiricilere güvenle açması, mikroservis mimarilerinin önüne ortak bir güvenlik duvarı çekilmesi ve kurumsal API'lerin paraya dönüştürülmesi (monetization) durumlarında tercih edilir.

#### **5\. Ekosistem Entegrasyonu**

Cloud Load Balancing, Cloud IAM, Vertex AI Agent Builder ve Chronicle Security ile derin entegrasyona sahiptir4.

### **Google Maps Platform APIs (Geocoding, Places, Routes)**

#### **1\. Ne Nedir?**

Google Maps Platform, Google'ın dünya çapındaki zengin coğrafi konum verilerini, adres dönüştürme (Geocoding), yer arama (Places) ve yol tarifi (Routes) API'leri aracılığıyla uygulamalara entegre eden küresel harita servisleri bütünüdür3.

#### **2\. Ne İşe Yarar?**

Uygulamaların adres doğrulama, iki nokta arasındaki en optimize rotayı hesaplama ve harita üzerinde görselleştirme gibi son derece karmaşık coğrafi veri işleme problemlerini sıfırdan çözmek zorunda kalmasını engeller. Google'ın anlık trafik ve güncel konum verisini doğrudan uygulamalara taşır.

#### **3\. Nasıl Kullanılır?**

Uygulamalar HTTP protokolü üzerinden ilgili API uç noktalarına çağrıda bulunur. Girdi olarak düz metin adres verildiğinde Geocoding API coğrafi koordinatları; bir koordinat veya isim girildiğinde Places API zengin lokasyon detaylarını; başlangıç ve bitiş noktası verildiğinde ise Routes API trafik durumu analiz edilmiş en hızlı rotayı çıktı olarak üretir.

#### **4\. Tipik Kullanım Senaryoları**

Kurye ve lojistik uygulamalarında teslimat rotalarının optimize edilmesi, e-ticaret sitelerinde kullanıcıların adres bilgilerini otomatik tamamlaması ve en yakın mağaza konumlarının kullanıcıya gösterilmesi durumlarında tercih edilir.

#### **5\. Ekosistem Entegrasyonu**

Vertex AI Agent Builder, Cloud Run, BigQuery ve Firebase Platformu ile doğrudan entegre çalışabilir3.

### **Google Workspace APIs (Gmail, Drive, Sheets, Docs API)**

#### **1\. Ne Nedir?**

Google Workspace API'leri; Gmail, Google Drive, Google Sheets ve Google Docs gibi popüler ofis ve üretkenlik uygulamalarına programatik erişim sunarak, bu platformlar üzerinde otomatik veri işlemleri yapılmasını sağlayan API setidir3.

#### **2\. Ne İşe Yarar?**

Çalışanların kurumsal belgeler oluşturma, e-posta gönderme ve veri tablolarını güncelleme gibi zaman alıcı, manuel ve tekrarlayan iş süreçlerini otomatize ederek insan hatalarını azaltır ve iş verimliliğini artırır3.

#### **3\. Nasıl Kullanılır?**

Uygulamalar OAuth 2.0 kimlik doğrulama katmanı üzerinden izin alarak Workspace API uç noktalarına bağlanır14. Sistem, girdi olarak tetiklenen bir alarm durumunda Gmail API'sini kullanarak otomatik e-posta gönderebilir; Drive API ile kurumsal klasörleri yönetebilir; Sheets API ile tablolara yeni satırlar ekleyebilir veya Docs API ile dinamik rapor dosyaları (çıktı) üretebilir3.

#### **4\. Tipik Kullanım Senaryoları**

Yapay zeka asistanlarının gelen e-postaları analiz edip otomatik yanıt taslakları oluşturması, sistem raporlarının her gece düzenli olarak bir Google Sheets belgesine yazılması ve şablon belgelerden otomatik sözleşmeler üretilmesi senaryolarında kullanılır3.

#### **5\. Ekosistem Entegrasyonu**

Vertex AI Agent Builder, AppSheet, Cloud Run Functions ve Cloud IAM ile doğrudan entegrasyon yeteneklerine sahiptir3.

### **AppSheet**

#### **1\. Ne Nedir?**

AppSheet, teknik kod yazma becerisine sahip olmayan iş analistlerinin veya departman yöneticilerinin kurumsal veri kaynaklarını kullanarak işlevsel mobil ve web uygulamaları geliştirmesini sağlayan, yapay zeka destekli bir kodsuz (no-code) uygulama geliştirme platformudur.

#### **2\. Ne İşe Yarar?**

Şirketlerin operasyonel süreçlerinde ihtiyaç duyduğu küçük ölçekli iş uygulamalarını geliştirmek için yazılım ekiplerinin haftalarca meşgul edilmesi problemini çözer. Uygulama geliştirme sürelerini günlerden saatlere indirerek kurumsal çevikliği ve dijital dönüşümü hızlandırır.

#### **3\. Nasıl Kullanılır?**

Kullanıcı girdi olarak mevcut bir veri kaynağını (Google Sheets, BigQuery, SQL veritabanı) AppSheet platformuna bağlar12. AppSheet'in akıllı motoru verinin yapısını analiz ederek otomatik olarak çalışan bir mobil/web uygulama arayüzü oluşturur. Kullanıcı sürükle-bırak yöntemleriyle form alanlarını, onay akışlarını ve bildirimleri yapılandırarak uygulamayı çıktı olarak yayına alır.

#### **4\. Tipik Kullanım Senaryoları**

Saha ekipleri için envanter sayım ve denetim formları, şirket içi izin onay akışları, masraf ve seyahat talep takipleri ile anlık görev atama uygulamaları için en uygun çözümdür.

#### **5\. Ekosistem Entegrasyonu**

Google Sheets, Google Drive, BigQuery, Cloud SQL, Apigee ve Google Workspace ile doğrudan entegrasyonu bulunur12.

## **8\. Kurumsal Mimari Karşılaştırmalı Karar Matrisleri**

Kurumsal mimari tasarımlarında benzer işlevlere sahip servislerin doğru senaryolarda seçilmesi, finansal verimlilik ve sistem performansı açısından kritik önem taşır. Aşağıdaki tablolar, hesaplama ve veritabanı katmanlarındaki anahtar servislerin seçim kriterlerini özetlemektedir.

### **Hesaplama ve Konteyner Servisleri Karşılaştırma Matrisi**

| Özellik | Compute Engine | Cloud Run | Google Kubernetes Engine (GKE) | App Engine | Cloud Run Functions |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **Soyutlama Seviyesi** | Düşük (IaaS)19 | Yüksek (Sunucusuz Konteyner)20 | Orta (Yönetilen Kubernetes)27 | Yüksek (PaaS)19 | Çok Yüksek (FaaS)16 |
| **Ölçekleme Hızı** | Dakikalar düzeyinde | Saniyeler düzeyinde (Sıfıra Ölçekleme)20 | Saniyeler/Dakikalar düzeyinde | Saniyeler düzeyinde | Milisaniyeler düzeyinde16 |
| **Dağıtım Yapısı** | VM İmajı (Örn: Packer)19 | Konteyner İmajı / Kaynak Kod20 | Konteyner İmajı (Pod)22 | Kaynak Kod (app.yaml) | Sadece Fonksiyon Kodu16 |
| **Faturalandırma** | Saniye bazlı (VM açık kaldığı sürece) | 100ms hassasiyetli (Sadece istek işlenirken)21 | VM kaynak tüketimi bazlı22 | Örnek çalışma saati bazlı19 | Milisaniye bazlı (Sadece tetiklendiğinde)16 |
| **En Uygun Senaryo** | Lift-and-Shift, özel işletim sistemi ve HPC iş yükleri. | Web uygulamaları, mikroservisler, API'ler ve hafif işler20. | Karmaşık mikroservis ağları, çoklu bulut ve hibrit yapılar22. | Standart monolitik web uygulamaları ve hızlı prototipler19. | Olay tetiklemeli veri işleme ve basit arka plan işleri16. |

### **İlişkisel ve NoSQL Veritabanı Sistemleri Seçim Kriterleri**

| Özellik | Cloud SQL | AlloyDB for PostgreSQL | Cloud Spanner | Cloud Firestore | Cloud Bigtable |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **Veri Modeli** | İlişkisel (MySQL, PostgreSQL, SQL Server)23 | İlişkisel (PostgreSQL ile %100 Uyumlu)11 | İlişkisel (Güçlü Tutarlılık)23 | NoSQL Belge (JSON benzeri)28 | NoSQL Geniş Sütun28 |
| **Maksimum Depolama** | 64 TB12 | 128 TB11 | Sınırsız23 | Sınırsız | Petabaytlar düzeyinde |
| **Yatay Yazma Ölçeği** | Yok (Yalnızca dikey ölçekleme)12 | Yok (Okuma havuzları yatay ölçeklenir)11 | Var (Sınırsız yatay yazma ölçeği)23 | Var (Otomatik ölçekleme) | Var (Düğümler arası doğrusal ölçekleme) |
| **Kullanılabilirlik SLA** | %99.95 (Yüksek Kullanılabilirlik aktifken)11 | %99.99 (Bakım pencereleri dahil)11 | %99.999 (Çoklu bölge kurulumlarında)23 | %99.999 | %99.999 (Çoklu bölge kurulumlarında) |
| **En Uygun Senaryo** | Genel amaçlı kurumsal uygulamalar ve e-ticaret23. | Ağır yük altındaki işlemsel ve analitik Postgres işleri11. | Küresel ölçekte çalışan finans ve envanter sistemleri23. | Canlı sohbet, mobil arka plan ve gerçek zamanlı veri senkronizasyonu. | IoT telemetrisi, zaman serisi analizi ve özellik depoları. |

## **9\. Stratejik Sonuç ve Gelecek Yol Haritası Öngörüleri**

Google Cloud Platform ve bağlantılı Google teknolojileri ekosistemi, modern kurumsal yazılım ihtiyaçlarına yanıt veren son derece entegre bir mimari sunmaktadır. Analiz edilen tüm servislerin ortak çalışma mekanizmaları incelendiğinde, bulut mimarisinin geleceğinin "akıllı otonom sistemler" ve "ayrıştırılmış altyapılar" üzerinde şekillendiği görülmektedir.  
Sistem tasarımlarında geleneksel monolitik yapılardan kurtulmak adına, hesaplama katmanında sunucusuz ve konteyner odaklı yaklaşım önceliklendirilmeli; mikroservisler ve API'ler için operasyonel yükü minimuma indiren, kullanılmadığında maliyeti sıfırlayan Cloud Run tercih edilmelidir20. Geliştirilen bu mikroservislerin harici dünya ile güvenli konuşması ve kurumsal güvenlik politikalarıyla denetlenmesi amacıyla ön katmanda mutlaka Apigee API Management ve Google Cloud Armor konumlandırılmalıdır4.  
Yapay zeka katmanında ise, Gemini Enterprise Agent Platform (Vertex AI Agent Builder) ile kurumsal entegrasyon sağlanırken, yüksek hacimli ve gerçek zamanlı işlemlerde gecikme sürelerini minimumda tutmak ve operasyonel maliyetleri düşürmek adına Gemini 3.1 Flash-Lite modelinin çıkarım ve araç çağırma katmanında öncelikli olarak kullanılması kurumsal sistemlerin verimliliğini maksimuma çıkaracaktır13. Veri mühendisliği tarafında ise BigQuery ve Datastream ikilisi ile kurulan gerçek zamanlı CDC veri hatları, Looker entegrasyonuyla birleştiğinde anlık iş kararlarının alınmasında kurumlara eşsiz bir çeviklik kazandırmaktadır12.

#### **Alıntılanan çalışmalar**

> 1. Vertex AI Agent Builder documentation, [https://docs.cloud.google.com/agent-builder](https://docs.cloud.google.com/agent-builder)  
> 2. More ways to build and scale AI agents with Vertex AI Agent Builder | Google Cloud Blog, [https://cloud.google.com/blog/products/ai-machine-learning/more-ways-to-build-and-scale-ai-agents-with-vertex-ai-agent-builder](https://cloud.google.com/blog/products/ai-machine-learning/more-ways-to-build-and-scale-ai-agents-with-vertex-ai-agent-builder)  
> 3. Vertex AI Agent Builder: Complete Guide for Building, Scaling, and Governing AI Agents in 2026 \- Engini AI, [https://engini.ai/blog/vertex-ai-agent-builder-guide-2026](https://engini.ai/blog/vertex-ai-agent-builder-guide-2026)  
> 4. Beyond the Chatbot: Building Autonomous AI Agents with Vertex AI and Gemini, [https://discuss.google.dev/t/beyond-the-chatbot-building-autonomous-ai-agents-with-vertex-ai-and-gemini/269343](https://discuss.google.dev/t/beyond-the-chatbot-building-autonomous-ai-agents-with-vertex-ai-and-gemini/269343)  
> 5. New Enhanced Tool Governance in Vertex AI Agent Builder | Google Cloud Blog, [https://cloud.google.com/blog/products/ai-machine-learning/new-enhanced-tool-governance-in-vertex-ai-agent-builder](https://cloud.google.com/blog/products/ai-machine-learning/new-enhanced-tool-governance-in-vertex-ai-agent-builder)  
> 6. Building AI Agents with Vertex AI Agent Builder | Google Codelabs, [https://codelabs.developers.google.com/devsite/codelabs/building-ai-agents-vertexai](https://codelabs.developers.google.com/devsite/codelabs/building-ai-agents-vertexai)  
> 7. Google Expands Gemini and Generative AI at Google Cloud Next \- WWT, [https://www.wwt.com/blog/google-expands-gemini-and-generative-ai-at-google-cloud-next](https://www.wwt.com/blog/google-expands-gemini-and-generative-ai-at-google-cloud-next)  
> 8. Dive deeper into your documents with Search Tuning using Google, [https://www.doit.com/blog/dive-deeper-into-your-documents-with-search-tuning-using-google-cloud-vertex-ai-agent-builder](https://www.doit.com/blog/dive-deeper-into-your-documents-with-search-tuning-using-google-cloud-vertex-ai-agent-builder)  
> 9. Building an AI Agent with Vertex AI Agent Builder (Part 1\) | by Thu Ya Kyaw | Google Cloud, [https://medium.com/google-cloud/building-an-ai-agent-with-vertex-ai-agent-builder-part-1-ad40246b7609](https://medium.com/google-cloud/building-an-ai-agent-with-vertex-ai-agent-builder-part-1-ad40246b7609)  
> 10. Vertex AI Agent Builder Tutorial & Review | Beginner-Friendly Guide \- YouTube, [https://www.youtube.com/watch?v=JePhyZ8luSI](https://www.youtube.com/watch?v=JePhyZ8luSI)  
> 11. Inside AlloyDB: Google Cloud's Database for PostgreSQL Workloads \- Cloudchipr, [https://cloudchipr.com/blog/alloydb](https://cloudchipr.com/blog/alloydb)  
> 12. Comparing Cloud SQL (PostgreSQL) vs AlloyDB vs Cloud Spanner \- Gist \- GitHub, [https://gist.github.com/Weiyuan-Lane/8daeabab1371221a286f0131cab3065d](https://gist.github.com/Weiyuan-Lane/8daeabab1371221a286f0131cab3065d)  
> 13. Gemini 3.1 Flash-Lite is now generally available | Google Cloud Blog, [https://cloud.google.com/blog/products/ai-machine-learning/gemini-3-1-flash-lite-is-now-generally-available](https://cloud.google.com/blog/products/ai-machine-learning/gemini-3-1-flash-lite-is-now-generally-available)  
> 14. Google Cloud latest news and announcements, [https://cloud.google.com/blog/topics/inside-google-cloud/whats-new-google-cloud](https://cloud.google.com/blog/topics/inside-google-cloud/whats-new-google-cloud)  
> 15. Gemini 3.1 Flash TTS on Google Cloud, [https://cloud.google.com/blog/products/ai-machine-learning/gemini-3-1-flash-tts-on-google-cloud](https://cloud.google.com/blog/products/ai-machine-learning/gemini-3-1-flash-tts-on-google-cloud)  
> 16. Cloud Run functions \- Google Cloud, [https://cloud.google.com/functions](https://cloud.google.com/functions)  
> 17. Migrate SQL Server to Cloud SQL for PostgreSQL and AlloyDB for PostgreSQL \- Cloud Solutions \- Google Cloud Platform, [https://googlecloudplatform.github.io/cloud-solutions/migrate-from-azure-to-google-cloud/migrate-sql-server-to-cloud-sql-and-alloydb-postgresql/](https://googlecloudplatform.github.io/cloud-solutions/migrate-from-azure-to-google-cloud/migrate-sql-server-to-cloud-sql-and-alloydb-postgresql/)  
> 18. Cloud Run function triggers | Google Cloud Documentation, [https://docs.cloud.google.com/run/docs/function-triggers](https://docs.cloud.google.com/run/docs/function-triggers)  
> 19. Google Cloud Platform Services Summary, [https://cloud.google.com/terms/services-20210126](https://cloud.google.com/terms/services-20210126)  
> 20. Cloud Run | Google Cloud, [https://cloud.google.com/run](https://cloud.google.com/run)  
> 21. Serverless | Google Cloud, [https://cloud.google.com/serverless](https://cloud.google.com/serverless)  
> 22. Cloud CISO Perspectives: February 2023 | Google Cloud Blog, [https://cloud.google.com/blog/products/identity-security/cloud-ciso-perspectives-february-2023](https://cloud.google.com/blog/products/identity-security/cloud-ciso-perspectives-february-2023)  
> 23. How to Choose Between Cloud SQL Cloud Spanner and AlloyDB \- OneUptime, [https://oneuptime.com/blog/post/2026-02-17-how-to-choose-between-cloud-sql-cloud-spanner-and-alloydb-for-your-database-workload/view](https://oneuptime.com/blog/post/2026-02-17-how-to-choose-between-cloud-sql-cloud-spanner-and-alloydb-for-your-database-workload/view)  
> 24. The Node.js runtime | Cloud Run \- Google Cloud Documentation, [https://docs.cloud.google.com/run/docs/runtimes/nodejs](https://docs.cloud.google.com/run/docs/runtimes/nodejs)  
> 25. Cloud Run functions runtimes | Google Cloud Documentation, [https://docs.cloud.google.com/run/docs/runtimes/function-runtimes](https://docs.cloud.google.com/run/docs/runtimes/function-runtimes)  
> 26. Functions best practices | Cloud Run, [https://docs.cloud.google.com/run/docs/tips/functions-best-practices](https://docs.cloud.google.com/run/docs/tips/functions-best-practices)  
> 27. GCP Professional Cloud Architect Study Plan 2026: My 10-Week, [https://www.examcert.app/blog/gcp-pca-study-plan-2026/](https://www.examcert.app/blog/gcp-pca-study-plan-2026/)  
> 28. Your Google Cloud database options, explained, [https://cloud.google.com/blog/topics/developers-practitioners/your-google-cloud-database-options-explained](https://cloud.google.com/blog/topics/developers-practitioners/your-google-cloud-database-options-explained)  
> 29. Databases in GCP \- KodeKloud, [https://notes.kodekloud.com/docs/GCP-Cloud-Digital-Leader-Certification/Database/Databases-in-GCP/page](https://notes.kodekloud.com/docs/GCP-Cloud-Digital-Leader-Certification/Database/Databases-in-GCP/page)  
> 30. Google Security Operations roles and permissions | Identity and Access Management (IAM), [https://docs.cloud.google.com/iam/docs/roles-permissions/chronicle](https://docs.cloud.google.com/iam/docs/roles-permissions/chronicle)