# حاوية VLESS لـ Google Cloud Run

هذه النسخة تستبدل تطبيق SSH الموجود في الحزمة الأصلية بخادم **Xray/VLESS عبر WebSocket**. طبقة HTTPS/TLS تكون خارج الحاوية عبر Cloud Run، لذلك لا تُضع شهادات TLS داخل إعداد Xray.

> **مهم:** Cloud Run يدعم WebSocket، لكن الاتصال يخضع لمهلة الطلب؛ اضبط المهلة إلى الحد المناسب، وتوقع إعادة الاتصال عند انتهاء المهلة. كما أن Cloud Run لا يوفّر عنوان TCP ثابتًا لهذه الحاوية؛ هذا التصميم مخصص لـ VLESS + WebSocket خلف HTTPS.

## المتطلبات

تحتاج إلى مشروع Google Cloud مفعّل عليه Cloud Run وArtifact Registry، وحساب لديه الصلاحيات اللازمة، ونطاق تملكه. يجب أن يكون النطاق موجّهًا إلى خدمة Cloud Run بعد إنشاء الربط. لا تضع كلمات المرور أو مفاتيح الخدمة داخل المستودع.

## البناء والنشر

استبدل القيم بين الأقواس:

```bash
gcloud auth login
gcloud config set project PROJECT_ID

gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

gcloud artifacts repositories create xray --repository-format=docker --location=REGION

UUID="$(cat /proc/sys/kernel/random/uuid)"
IMAGE="REGION-docker.pkg.dev/PROJECT_ID/xray/vless:latest"

gcloud builds submit --tag "$IMAGE" .

gcloud run deploy vless \
  --image "$IMAGE" \
  --region REGION \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --timeout 3600 \
  --concurrency 1000 \
  --min 1 \
  --set-env-vars "VLESS_UUID=$UUID,WS_PATH=/_vless"
```

يجب حفظ قيمة `UUID` لأنها جزء من رابط اتصال VLESS. لا تُرسلها علنًا ولا تضعها في Git. يمكن بدلًا من ذلك تمريرها عبر Secret Manager في بيئة إنتاجية.

## ربط الدومين

بعد نشر الخدمة، استخدم Cloud Run Domain Mapping أو موازن HTTPS عالمي. الربط المباشر بالنطاق في Cloud Run متاح في مناطق محددة وحالته Preview، بينما توصي Google بموازن HTTPS عالمي للإنتاج. مثال الربط المباشر:

```bash
gcloud beta run domain-mappings create \
  --service vless \
  --domain vless.example.com \
  --region REGION

gcloud beta run domain-mappings describe \
  --domain vless.example.com \
  --region REGION
```

أضف سجلات DNS التي يعرضها أمر `describe` لدى مزود النطاق. لا تستخدم عنوان `run.app` بدلًا من النطاق النهائي في إعداد العميل إذا كنت تريد شهادة TLS الخاصة بـ Cloud Run.

## بيانات العميل

بعد اكتمال DNS وشهادة HTTPS، تكون القيم:

| الحقل | القيمة |
|---|---|
| البروتوكول | VLESS |
| العنوان | `vless.example.com` |
| المنفذ | `443` |
| التشفير | `none` داخل VLESS، مع HTTPS/TLS من Cloud Run |
| النقل | WebSocket |
| المسار | `/_vless` |
| UUID | القيمة التي ولّدتها أثناء النشر |
| SNI/Host | `vless.example.com` |
| Allow insecure | `false` |

رابط URI عام، بعد استبدال القيم، يكون على النمط التالي:

```text
vless://UUID@vless.example.com:443?encryption=none&security=tls&type=ws&host=vless.example.com&path=%2F_vless&sni=vless.example.com#cloud-run-vless
```

## ملاحظات تشغيلية

لا تُشغّل هذه الحاوية مع إعداد SSH الأصلي، ولا تضع Telegram token فيها. إذا كان الاستخدام يحتاج TCP/Reality أو جلسات طويلة بلا مهلة Cloud Run، فاستخدم Compute Engine بدل Cloud Run؛ فذلك يتطلب خادمًا بقدرة شبكة مختلفة.

## المصدر الأصلي

الملف المرفق كان تطبيق SSH/WebSocket، وليس Xray أو VLESS. هذه الحزمة الجديدة مستقلة عنه وتحتوي فقط على Dockerfile وإعداد Xray ونقطة تشغيل وملف نشر.

## النشر الآمن باستخدام Google Secret Manager

الطريقة الموصى بها هي استخدام السكربت `deploy-cloudrun-secrets.sh`. سيطلب UUID في الطرفية بشكل مخفي، ينشئ أو يحدّث السر في Secret Manager، يمنح حساب تشغيل Cloud Run صلاحية قراءته، ثم ينشر الصورة مع `--set-secrets`. لا يتم وضع UUID في Dockerfile أو داخل الصورة.

```bash
chmod +x deploy-cloudrun-secrets.sh
PROJECT_ID="PROJECT_ID" REGION="europe-west1" SERVICE="vless" ./deploy-cloudrun-secrets.sh
```

إذا كان مستودع Artifact Registry موجودًا في منطقة أخرى، استعمل نفس المنطقة في `REGION`. يبقى Docker Hub مستقلًا عن هذا السر؛ تسجيل الدخول إلى Docker Hub مطلوب فقط إذا كنت سترفع الصورة إلى Docker Hub، ولا يحتاجه Cloud Build عندما تبني الصورة مباشرة إلى Artifact Registry.

يمكن تدوير السر لاحقًا بإضافة إصدار جديد:

```bash
printf '%s' 'UUID-الجديد' | gcloud secrets versions add vless-uuid --data-file=-
gcloud run services update vless --region europe-west1 --update-secrets VLESS_UUID=vless-uuid:latest
```

## تدفق بوت Telegram

بعد تشغيل الحاوية، افتح الدومين في المتصفح. ستظهر صفحة إعداد بوت VLESS. أدخل `ADMIN_PASSWORD`، ثم توكن البوت والدومين و`Admin Chat ID` اختياريًا. التوكن يُستخدم في ذاكرة العملية ولا يظهر في الصفحة أو السجلات؛ في الإنتاج الأفضل تمريره من Secret Manager عبر `TELEGRAM_BOT_TOKEN` بدل إدخاله من الصفحة.

بعد التفعيل، افتح البوت في Telegram واستعمل `/vless` لإرسال رابط VLESS، أو `/status` لعرض الحالة، أو `/help` لعرض الأوامر. المشروع الآن لا يشغّل SSH ولا Dropbear ولا يرسل SSH payload؛ Nginx يمرر مسار `/_vless` إلى Xray، ويمرر لوحة الإعداد إلى التطبيق الداخلي.

للتشغيل يجب توفير `ADMIN_PASSWORD` و`VLESS_UUID`. مثال Cloud Run:

```bash
gcloud run deploy vless \
  --image docker.io/knhfdsjj/blessvless:v1 \
  --port 8080 \
  --allow-unauthenticated \
  --timeout 3600 \
  --set-env-vars "DOMAIN=vless.example.com,WS_PATH=/_vless" \
  --set-secrets "ADMIN_PASSWORD=admin-password:latest,VLESS_UUID=vless-uuid:latest"
```
