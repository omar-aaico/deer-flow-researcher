# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Default output schema for person research.
Used when no custom schema is provided.
"""

DEFAULT_PERSON_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Full name of the person"
        },
        "title": {
            "type": "string",
            "description": "Current job title"
        },
        "company": {
            "type": "string",
            "description": "Current company/organization"
        },
        "location": {
            "type": "string",
            "description": "Current location (city, state/country)"
        },
        "linkedin_url": {
            "type": "string",
            "description": "LinkedIn profile URL"
        },
        "email": {
            "type": "string",
            "description": "Professional email address if available"
        },
        "phone": {
            "type": "string",
            "description": "Phone number if publicly available"
        },
        "background": {
            "type": "string",
            "description": "Professional background and career history summary"
        },
        "recent_activities": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Recent professional activities, projects, or initiatives"
        },
        "tech_stack": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Technologies, tools, or platforms they work with"
        },
        "pain_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Potential business challenges or pain points they may face"
        },
        "social_media": {
            "type": "object",
            "properties": {
                "twitter": {"type": "string"},
                "github": {"type": "string"},
                "website": {"type": "string"}
            },
            "description": "Social media and professional profiles"
        }
    },
    "required": ["name", "title", "company"],
    "additionalProperties": True
}


# Schema for candidate disambiguation
CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique identifier for this candidate (e.g., candidate_1, candidate_2)"
                    },
                    "name": {
                        "type": "string",
                        "description": "Full name"
                    },
                    "title": {
                        "type": "string",
                        "description": "Current job title"
                    },
                    "company": {
                        "type": "string",
                        "description": "Current company"
                    },
                    "location": {
                        "type": "string",
                        "description": "Location (city, state/country)"
                    },
                    "linkedin": {
                        "type": "string",
                        "description": "LinkedIn URL if found"
                    },
                    "summary": {
                        "type": "string",
                        "description": "Brief summary to help distinguish this person (50-100 words)"
                    }
                },
                "required": ["id", "name", "title", "company", "summary"]
            },
            "minItems": 1,
            "description": "List of distinct person candidates found"
        }
    },
    "required": ["candidates"]
}
