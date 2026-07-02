from skill_parser import parse_skill_md, slugify_skill_name


def test_parse_skill_md_infers_name_and_description_from_chinese_sections():
    content = """# Writing Coach

## 何时使用

- 当用户要写公众号文章
- 当用户要润色中文文本

## 工作流

先判断目标读者，再生成提纲。
"""

    result = parse_skill_md(content)

    assert result["name"] == "writing-coach"
    assert "公众号文章" in result["description"]
    assert result["triggers"]


def test_slugify_skill_name_keeps_valid_ascii_slug():
    assert slugify_skill_name("Skill Manager!") == "skill-manager"
