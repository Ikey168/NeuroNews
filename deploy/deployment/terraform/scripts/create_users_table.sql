-- Create users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'editor', 'user')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    password_changed_at TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMP,
    reset_token VARCHAR(255),
    reset_token_expires TIMESTAMP
);

-- Create index on email for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- Create index on role for RBAC queries
CREATE INDEX IF NOT EXISTS idx_users_role ON users (role);

-- Create audit table for user events
CREATE TABLE IF NOT EXISTS user_audit_log (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    ip_address VARCHAR(45),
    user_agent VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create index for user audit queries
CREATE INDEX IF NOT EXISTS idx_user_audit_user_id ON user_audit_log (user_id);
CREATE INDEX IF NOT EXISTS idx_user_audit_event_type ON user_audit_log (event_type);

-- Create function to update password_changed_at
CREATE OR REPLACE FUNCTION update_password_changed_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.password_hash != OLD.password_hash THEN
        NEW.password_changed_at = CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for password changes
CREATE TRIGGER password_update
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_password_changed_at();

-- Create function to log user events
CREATE OR REPLACE FUNCTION log_user_event(
    p_user_id BIGINT,
    p_event_type VARCHAR,
    p_event_data JSONB,
    p_ip_address VARCHAR,
    p_user_agent VARCHAR
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO user_audit_log (
        user_id,
        event_type,
        event_data,
        ip_address,
        user_agent
    ) VALUES (
        p_user_id,
        p_event_type,
        p_event_data,
        p_ip_address,
        p_user_agent
    );
END;
$$ LANGUAGE plpgsql;

-- Create admin role function
CREATE OR REPLACE FUNCTION create_admin_user(
    p_email VARCHAR,
    p_password_hash VARCHAR,
    p_first_name VARCHAR,
    p_last_name VARCHAR
)
RETURNS BIGINT AS $$
DECLARE
    v_user_id BIGINT;
BEGIN
    INSERT INTO users (
        email,
        password_hash,
        first_name,
        last_name,
        role
    ) VALUES (
        p_email,
        p_password_hash,
        p_first_name,
        p_last_name,
        'admin'
    ) RETURNING id INTO v_user_id;
    
    RETURN v_user_id;
END;
$$ LANGUAGE plpgsql;

-- Create user validation function
CREATE OR REPLACE FUNCTION validate_user_login(
    p_email VARCHAR
)
RETURNS TABLE (
    can_login BOOLEAN,
    lock_message VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        CASE 
            WHEN NOT is_active THEN FALSE
            WHEN locked_until IS NOT NULL AND locked_until > CURRENT_TIMESTAMP THEN FALSE
            ELSE TRUE
        END,
        CASE 
            WHEN NOT is_active THEN 'Account is disabled'
            WHEN locked_until IS NOT NULL AND locked_until > CURRENT_TIMESTAMP 
                THEN 'Account is locked. Try again later'
            ELSE NULL
        END
    FROM users
    WHERE email = p_email;
END;
$$ LANGUAGE plpgsql;

-- Grant appropriate permissions
GRANT SELECT, INSERT, UPDATE ON users TO api_user;
GRANT SELECT, INSERT ON user_audit_log TO api_user;
GRANT EXECUTE ON FUNCTION log_user_event TO api_user;
GRANT EXECUTE ON FUNCTION validate_user_login TO api_user;

-- Grant admin permissions
GRANT ALL ON users TO admin_user;
GRANT ALL ON user_audit_log TO admin_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO admin_user;