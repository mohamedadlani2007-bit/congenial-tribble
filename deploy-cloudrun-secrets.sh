#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?استعمل: PROJECT_ID=... REGION=... SERVICE=... ./deploy-cloudrun-secrets.sh}"
: "${REGION:?استعمل: PROJECT_ID=... REGION=... SERVICE=... ./deploy-cloudrun-secrets.sh}"
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

SECRET_NAME="${SERVICE}-uuid"
if gcloud secrets describe "$SECRET_NAME" >/dev/null 2>&1; then
  echo "سيتم تحديث سر ${SECRET_NAME}. أدخل UUID جديدًا أو اضغط Ctrl-D للإبقاء على الموجود."
  read -r -s -p 'VLESS UUID: ' UUID || true
  echo
  if [ -n "${UUID:-}" ]; then
    printf '%s' "$UUID" | gcloud secrets versions add "$SECRET_NAME" --data-file=-
  fi
else
  read -r -s -p 'VLESS UUID (اتركه فارغًا لإنشاء UUID تلقائيًا): ' UUID
  echo
  UUID="${UUID:-$(cat /proc/sys/kernel/random/uuid)}"
  printf '%s' "$UUID" | gcloud secrets create "$SECRET_NAME" --data-file=-
fi

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role='roles/secretmanager.secretAccessor' >/dev/null

gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --timeout 3600 \
  --concurrency 1000 \
  --min 1 \
  --set-env-vars "WS_PATH=${WS_PATH}" \
  --set-secrets "VLESS_UUID=${SECRET_NAME}:latest"

echo "تم النشر. السر محفوظ في Secret Manager باسم: ${SECRET_NAME}"
