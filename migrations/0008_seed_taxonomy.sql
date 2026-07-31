-- 0008 · 기본 통합 택소노미 시드(§5.3) — 카테고리 매핑의 목적지
-- ltree path 는 slug 를 라벨로 사용(영숫자/언더스코어).

-- 루트 카테고리
INSERT INTO core.categories (parent_id, slug, name_ko, name_en, path) VALUES
    (NULL, 'electronics', '가전·전자', 'Electronics', 'electronics'),
    (NULL, 'fashion',     '패션·의류', 'Fashion',     'fashion'),
    (NULL, 'beauty',      '뷰티·화장품','Beauty',      'beauty'),
    (NULL, 'health',      '건강·헬스', 'Health',      'health'),
    (NULL, 'home',        '홈·리빙',   'Home',        'home'),
    (NULL, 'food',        '식품',      'Food',        'food'),
    (NULL, 'digital',     '디지털',    'Digital',     'digital'),
    (NULL, 'baby',        '유아·출산', 'Baby',        'baby'),
    (NULL, 'sports',      '스포츠·레저','Sports',      'sports'),
    (NULL, 'pet',         '반려동물',  'Pet',         'pet')
ON CONFLICT (slug) DO NOTHING;

-- 하위 카테고리(parent 를 slug 로 조회)
INSERT INTO core.categories (parent_id, slug, name_ko, name_en, path)
SELECT p.id, x.slug, x.name_ko, x.name_en, (p.path::text || '.' || x.leaf)::ltree
FROM (VALUES
    ('electronics','electronics.appliance','주방·생활가전','Appliances','appliance'),
    ('electronics','electronics.computer', '컴퓨터·노트북','Computers','computer'),
    ('electronics','electronics.mobile',   '휴대폰·태블릿','Mobile','mobile'),
    ('beauty',     'beauty.skincare',      '스킨케어','Skincare','skincare'),
    ('beauty',     'beauty.makeup',        '메이크업','Makeup','makeup'),
    ('health',     'health.supplement',    '영양제·보충제','Supplements','supplement'),
    ('digital',    'digital.ebook',        '전자책','E-book','ebook'),
    ('digital',    'digital.software',     '소프트웨어','Software','software'),
    ('digital',    'digital.course',       '온라인 강의','Course','course')
) AS x(parent_slug, slug, name_ko, name_en, leaf)
JOIN core.categories p ON p.slug = x.parent_slug
ON CONFLICT (slug) DO NOTHING;
