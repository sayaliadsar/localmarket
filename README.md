# Local Market - malshiras 
1. Supabase madhe New Project banva
2. Storage > New Bucket > product-images (Public kara)
3. SQL Editor madhe tables auto-banatil (app.py init_db ne)
4. Render madhe New Web Service > GitHub Connect
5. Environment Variables taka:
   DATABASE_URL = postgres://...
   SUPABASE_URL = https://xxx.supabase.co
   SUPABASE_KEY = sb_secret_...
   SECRET_KEY = kahi-pan-secret
6. Start Command: gunicorn app:app --bind 0.0.0.0:$PORT