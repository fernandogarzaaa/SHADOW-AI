from setuptools import setup, find_packages

setup(
    name="ghost-adapter",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["pydantic>=2.10.0", "httpx>=0.28.0"],
    python_requires=">=3.11",
)
