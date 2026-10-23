-- Les codes promo passent aussi par /aller/promo/<id> (23/10/2026) : un clic = une offre OU un code promo.
ALTER TABLE clic_sortant ALTER COLUMN offre_id DROP NOT NULL;
ALTER TABLE clic_sortant ADD COLUMN IF NOT EXISTS promo_id bigint;
