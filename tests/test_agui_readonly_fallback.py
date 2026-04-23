from bin.agui_server import _build_read_only_tool_summary


def test_build_read_only_tool_summary_for_ecr_list():
    text = _build_read_only_tool_summary(
        "list_aws_resources",
        {
            "success": True,
            "resource_type": "ecr",
            "region": "ap-south-1",
            "count": 2,
            "items": [
                {
                    "repository_name": "langchain-agent",
                    "repository_uri": "123456789012.dkr.ecr.ap-south-1.amazonaws.com/langchain-agent",
                },
                {
                    "repository_name": "frontend",
                    "repository_uri": "123456789012.dkr.ecr.ap-south-1.amazonaws.com/frontend",
                },
            ],
        },
    )
    assert "I found 2 ECR resources in region ap-south-1" in text
    assert "langchain-agent" in text
    assert "frontend" in text
