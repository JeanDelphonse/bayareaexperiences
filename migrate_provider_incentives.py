"""
Migration: Provider Incentive Program
Adds performance commission columns + referral columns to providers table.
Creates provider_referral_codes table.

Run once:
    python migrate_provider_incentives.py
"""
from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    conn = db.engine.connect()
    dialect = db.engine.dialect.name  # 'sqlite' or 'mysql'

    # ── providers table: new columns ──────────────────────────────────────────
    alter_stmts = []

    if dialect == 'sqlite':
        alter_stmts = [
            "ALTER TABLE providers ADD COLUMN performance_commission_rate    DECIMAL(5,2)  DEFAULT NULL",
            "ALTER TABLE providers ADD COLUMN performance_months_consecutive SMALLINT      NOT NULL DEFAULT 0",
            "ALTER TABLE providers ADD COLUMN performance_locked_in          BOOLEAN       NOT NULL DEFAULT 0",
            "ALTER TABLE providers ADD COLUMN performance_last_evaluated     DATE          DEFAULT NULL",
            "ALTER TABLE providers ADD COLUMN referral_code                  VARCHAR(40)   DEFAULT NULL",
            "ALTER TABLE providers ADD COLUMN referral_credit_balance        DECIMAL(10,2) NOT NULL DEFAULT 0.00",
        ]
    else:  # MySQL
        alter_stmts = [
            "ALTER TABLE providers ADD COLUMN performance_commission_rate    DECIMAL(5,2)  DEFAULT NULL",
            "ALTER TABLE providers ADD COLUMN performance_months_consecutive TINYINT       NOT NULL DEFAULT 0",
            "ALTER TABLE providers ADD COLUMN performance_locked_in          TINYINT(1)    NOT NULL DEFAULT 0",
            "ALTER TABLE providers ADD COLUMN performance_last_evaluated     DATE          DEFAULT NULL",
            "ALTER TABLE providers ADD COLUMN referral_code                  VARCHAR(40)   DEFAULT NULL UNIQUE",
            "ALTER TABLE providers ADD COLUMN referral_credit_balance        DECIMAL(10,2) NOT NULL DEFAULT 0.00",
        ]

    for stmt in alter_stmts:
        col_name = stmt.split('ADD COLUMN')[1].strip().split()[0]
        try:
            conn.execute(db.text(stmt))
            print(f'  + Added column: {col_name}')
        except Exception as e:
            if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
                print(f'  ~ Column already exists: {col_name}')
            else:
                print(f'  ! Error adding {col_name}: {e}')

    # ── provider_referral_codes table ─────────────────────────────────────────
    if dialect == 'sqlite':
        create_table = """
        CREATE TABLE IF NOT EXISTS provider_referral_codes (
            referral_id              VARCHAR(9)     NOT NULL PRIMARY KEY,
            referrer_provider_id     VARCHAR(9)     NOT NULL REFERENCES providers(provider_id),
            referral_code            VARCHAR(40)    NOT NULL UNIQUE,
            referred_provider_id     VARCHAR(9)     REFERENCES providers(provider_id),
            referred_business_name   VARCHAR(200),
            status                   VARCHAR(20)    NOT NULL DEFAULT 'pending',
            referred_signup_at       DATETIME,
            bookings_completed       SMALLINT       NOT NULL DEFAULT 0,
            credit_amount            DECIMAL(8,2)   NOT NULL DEFAULT 100.00,
            credited_at              DATETIME,
            referrer_notified_at     DATETIME,
            created_at               DATETIME       NOT NULL
        )
        """
    else:  # MySQL
        create_table = """
        CREATE TABLE IF NOT EXISTS provider_referral_codes (
            referral_id              CHAR(9)        NOT NULL PRIMARY KEY,
            referrer_provider_id     CHAR(9)        NOT NULL,
            referral_code            VARCHAR(40)    NOT NULL UNIQUE,
            referred_provider_id     CHAR(9),
            referred_business_name   VARCHAR(200),
            status                   ENUM('pending','qualified','credited','expired') NOT NULL DEFAULT 'pending',
            referred_signup_at       DATETIME,
            bookings_completed       TINYINT        NOT NULL DEFAULT 0,
            credit_amount            DECIMAL(8,2)   NOT NULL DEFAULT 100.00,
            credited_at              DATETIME,
            referrer_notified_at     DATETIME,
            created_at               DATETIME       NOT NULL,
            CONSTRAINT fk_prc_referrer FOREIGN KEY (referrer_provider_id) REFERENCES providers(provider_id),
            CONSTRAINT fk_prc_referred FOREIGN KEY (referred_provider_id) REFERENCES providers(provider_id),
            INDEX ix_prov_ref_referrer (referrer_provider_id),
            INDEX ix_prov_ref_referred (referred_provider_id),
            INDEX ix_prov_ref_status   (status)
        )
        """

    try:
        conn.execute(db.text(create_table))
        print('  + Created table: provider_referral_codes')
    except Exception as e:
        print(f'  ! provider_referral_codes: {e}')

    conn.commit()
    conn.close()
    print('\nMigration complete.')
