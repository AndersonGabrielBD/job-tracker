from job_radar_common.stack_gate import is_other_stack, is_qa_role


def test_rejects_dotnet_posting():
    title = "Desenvolvedor Backend"
    description = "Experiencia com C#, .NET 6+, ASP.NET Core, Entity Framework"
    assert is_other_stack(title, description)


def test_rejects_dotnet_even_with_react_as_nice_to_have():
    title = "Desenvolvedor Backend .NET"
    description = "Backend em C# e .NET Core. Desejavel: React, TypeScript, Next.js"
    assert is_other_stack(title, description)


def test_rejects_php_and_delphi_and_salesforce():
    assert is_other_stack("Desenvolvedor PHP", "")
    assert is_other_stack("Desenvolvedor Delphi", "")
    assert is_other_stack("Salesforce Developer", "")


def test_does_not_false_positive_on_javascript():
    assert not is_other_stack("Desenvolvedor JavaScript", "React, Node.js, TypeScript")


def test_does_not_false_positive_on_python_stack():
    assert not is_other_stack("Desenvolvedor Python Backend", "FastAPI, Django, PostgreSQL")


def test_rejects_qa_titles():
    assert is_qa_role("QA Engineer")
    assert is_qa_role("Analista de Qualidade")
    assert is_qa_role("Tester Pleno")
    assert is_qa_role("SDET")


def test_does_not_false_positive_qa_on_backend_role():
    assert not is_qa_role("Desenvolvedor Backend Python")
