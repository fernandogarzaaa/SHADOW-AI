from setuptools import setup, find_packages

setup(
    name="ghost-adapter",
    version="0.1.0",
    description="Approval-gated local action executor and GHOST task adapter for SHADOW-AI.",
    author="Fernando Garza",
    license="MIT",
    packages=find_packages(include=["ghost_adapter", "ghost_adapter.*"], exclude=["tests", "tests.*"]),
    install_requires=["pydantic>=2.10.0,<3", "httpx>=0.28.0,<1"],
    python_requires=">=3.11",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
    ],
)
