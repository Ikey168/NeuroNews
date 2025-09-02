DROP TABLE IF EXISTS news_articles;

CREATE TABLE news_articles (
    id VARCHAR(255) DISTKEY PRIMARY KEY,
    source VARCHAR(255) NOT NULL,
    title VARCHAR(1000) NOT NULL,
    content VARCHAR(65535) NOT NULL,
    published_date TIMESTAMP NOT NULL SORTKEY,
    sentiment FLOAT,
    entities SUPER,  -- Using SUPER type for JSON-like storage of entities
    keywords SUPER   -- Using SUPER type for JSON-like storage of keywords
)
DISTSTYLE KEY;