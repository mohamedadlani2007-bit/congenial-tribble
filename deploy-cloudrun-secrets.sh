#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?استعمل: PROJECT_ID=... REGION=... DOMAIN=... ./deploy-cloudrun-secrets.sh}"
: "${REGION:?استعمل: PROJECT_ID=... REGION=... DOMAIN=... ./deploy-cloudrun-secrets.sh}"
: "${DOMAIN:?استعمل: PROJECT_ID=... REGION=... DOMAIN=... ./deploy-cloudrun-secrets.sh}"
: "${SERVICE:=vless}"
: "${REPO:=xray}"
: "${IMAGE_TAG:=v1}"
: "${WS_PATH:=/_vless}"

command -v gcloud >/dev/null || { echo 'gcloud غير موجود' >&2; exit 1; }
gcloud config set project "$PROJECT_ID" >/dev/null
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com

gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION"

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/blessvless:${IMAGE_TAG}"
gcloud builds submit --tag "$IMAGE" .

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

put_secret() {
  name="$1"
  prompt="$2"
  existing="${3:-}"
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    printf '%s\n' "تحديث اختياري للسر ${name}. اتركه فارغًا للإبقاء على الموجود."
    read -r -s -p "$prompt: " value || true
    echo
    if [ -n "${value:-}" ]; then
      printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=-
    fi
  else
    read -r -s -p "$prompt: " value
    echo
    if [ -z "${value:-}" ]; then
      echo "السر ${name} مطلوب" >&2
      exit 1
    fi
    printf '%s' "$value" | gcloud secrets create "$name" --data-file=-
  fi
  gcloud secrets add-iam-policy-binding "$name" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role='roles/secretmanager.secretAccessor' >/dev/null
}

UUID_SECRET="${SERVICE}-uuid"
if gcloud secrets describe "$UUID_SECRET" >/dev/null 2>&1; then
  printf '%s\n' "يوجد UUID محفوظ. اترك الإدخال فارغًا للإبقاء عليه."
  read -r -s -p 'UUID جديد اختياري: ' UUID || true
  echo
  if [ -n "${UUID:-}" ]; then
    printf '%s' "$UUID" | gcloud secrets versions add "$UUID_SECRET" --data-file=-
  fi
else
  UUID="$(cat /proc/sys/kernel/random/uuid)"
  printf '%s' "$UUID" | gcloud secrets create "$UUID_SECRET" --data-file=-
fi
gcloud secrets add-iam-policy-binding "$UUID_SECRET" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role='roles/secretmanager.secretAccessor' >/dev/null

put_secret "${SERVICE}-admin-password" 'كلمة سر لوحة إعداد البوت' "admin"

gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --timeout 3600 \
  --concurrency 1000 \
  --min 1 \
  --set-env-vars "DOMAIN=${DOMAIN},WS_PATH=${WS_PATH}" \
  --set-secrets "VLESS_UUID=${SERVICE}-uuid:latest,ADMIN_PASSWORD=${SERVICE}-admin-password:latest"

echo "تم النشر. افتح https://${DOMAIN} وأدخل توكن Telegram في صفحة إعداد البوت."
