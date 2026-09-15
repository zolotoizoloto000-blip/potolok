"""Storage adapter.
Local mode works immediately. Set SUPABASE_URL, SUPABASE_SERVICE_KEY and SUPABASE_BUCKET
to switch uploads to Supabase Storage at deployment time.
"""
import os
SUPABASE_URL=os.getenv("SUPABASE_URL","")
SUPABASE_SERVICE_KEY=os.getenv("SUPABASE_SERVICE_KEY","")
SUPABASE_BUCKET=os.getenv("SUPABASE_BUCKET","product-images")
def configured():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY and SUPABASE_BUCKET)
