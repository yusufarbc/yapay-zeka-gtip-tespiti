#!/bin/bash
# Cloud SQL gtip-db kurulum scripti
# Cloud SQL RUNNABLE olduktan sonra bu scripti çalıştırın

PROJECT=gtip-tespit-projesi
INSTANCE=gtip-db
SA=gtip-backend-sa@gtip-tespit-projesi.iam.gserviceaccount.com
DB_PASS="GtipSecure$(date +%Y%m%d)!"

echo "1. gtip_db veritabanı oluşturuluyor..."
gcloud sql databases create gtip_db --instance=$INSTANCE --project=$PROJECT

echo "2. postgres kullanıcısı şifre ayarlanıyor..."
gcloud sql users set-password postgres --instance=$INSTANCE --password="$DB_PASS" --project=$PROJECT

echo "3. Şifre Secret Manager'a ekleniyor..."
echo -n "$DB_PASS" | gcloud secrets create gtip-db-password --data-file=- --project=$PROJECT || \
    echo -n "$DB_PASS" | gcloud secrets versions add gtip-db-password --data-file=-

echo "4. SA'ya Secret erişimi veriliyor..."
gcloud secrets add-iam-policy-binding gtip-db-password \
    --member="serviceAccount:$SA" \
    --role=roles/secretmanager.secretAccessor \
    --project=$PROJECT

echo "5. DATABASE_URL env var Cloud Run Job'a ekleniyor..."
gcloud run jobs update gtip-btb-sync-job \
    --region=europe-west3 \
    --update-env-vars="DATABASE_URL=postgresql+psycopg2://postgres:${DB_PASS}@/gtip_db?host=/cloudsql/gtip-tespit-projesi:europe-west3:gtip-db" \
    --project=$PROJECT

echo ""
echo "=== KURULUM TAMAMLANDI ==="
echo "Şifre: $DB_PASS"
echo "NOT: Bu şifreyi güvenli bir yere kaydedin!"
echo ""
echo "Son test için:"
echo "  gcloud run jobs execute gtip-btb-sync-job --region=europe-west3"
