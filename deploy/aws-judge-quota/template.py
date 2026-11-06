"""Render a credential-free CloudFormation template for the shared demo counter."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

NAME = "bifang-public-demo-quota"


def render_template(source: str) -> dict:
    def ref(name):
        return {"Ref": name}
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Bifang public-demo reservation counter; no inference credentials or prompts",
        "Parameters": {
            "QuotaSecret": {"Type": "String", "NoEcho": True, "MinLength": 48},
            "ExpiresAt": {"Type": "String", "Default": "2026-12-23T20:00:00Z"},
            "RequestLimit": {"Type": "Number", "Default": 1000, "MinValue": 1},
            "OutputLimit": {"Type": "Number", "Default": 4000000, "MinValue": 1},
            "InputBytesLimit": {"Type": "Number", "Default": 16777216, "MinValue": 1},
            "PerMinute": {"Type": "Number", "Default": 60, "MinValue": 1},
        },
        "Resources": {
            "BudgetTable": {
                "Type": "AWS::DynamoDB::Table",
                "DeletionPolicy": "Retain",
                "UpdateReplacePolicy": "Retain",
                "Properties": {
                    "TableName": NAME,
                    "BillingMode": "PAY_PER_REQUEST",
                    "AttributeDefinitions": [{"AttributeName": "pk", "AttributeType": "S"}],
                    "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}],
                    "SSESpecification": {"SSEEnabled": True},
                    "TimeToLiveSpecification": {"AttributeName": "ttl", "Enabled": True},
                    "OnDemandThroughput": {"MaxReadRequestUnits": 20, "MaxWriteRequestUnits": 20},
                    "Tags": [{"Key": "Project", "Value": "Bifang"}],
                },
            },
            "Logs": {
                "Type": "AWS::Logs::LogGroup",
                "Properties": {"LogGroupName": "/aws/lambda/" + NAME, "RetentionInDays": 7},
            },
            "ExecutionRole": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": NAME,
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                                       "Action": "sts:AssumeRole"}],
                    },
                    "Policies": [{"PolicyName": "reserve-only", "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {"Effect": "Allow", "Action": "dynamodb:UpdateItem",
                             "Resource": {"Fn::GetAtt": ["BudgetTable", "Arn"]},
                             "Condition": {"ForAnyValue:StringEquals": {
                                 "dynamodb:EnclosingOperation": ["TransactWriteItems"]}}},
                            {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                             "Resource": {"Fn::GetAtt": ["Logs", "Arn"]}},
                        ],
                    }}],
                },
            },
            "QuotaFunction": {
                "Type": "AWS::Lambda::Function",
                "DependsOn": "Logs",
                "Properties": {
                    "FunctionName": NAME, "Runtime": "python3.12", "Handler": "index.handler",
                    "Role": {"Fn::GetAtt": ["ExecutionRole", "Arn"]},
                    "Code": {"ZipFile": source}, "MemorySize": 128, "Timeout": 10,
                    "Environment": {"Variables": {
                        "BIFANG_QUOTA_SECRET": ref("QuotaSecret"),
                        "BIFANG_QUOTA_TABLE": ref("BudgetTable"),
                        "BIFANG_QUOTA_EXPIRES_AT": ref("ExpiresAt"),
                        "BIFANG_QUOTA_REQUEST_LIMIT": ref("RequestLimit"),
                        "BIFANG_QUOTA_OUTPUT_LIMIT": ref("OutputLimit"),
                        "BIFANG_QUOTA_INPUT_BYTES_LIMIT": ref("InputBytesLimit"),
                        "BIFANG_QUOTA_PER_MINUTE": ref("PerMinute"),
                    }},
                    "Tags": [{"Key": "Project", "Value": "Bifang"}],
                },
            },
            "QuotaUrl": {
                "Type": "AWS::Lambda::Url",
                "Properties": {"TargetFunctionArn": ref("QuotaFunction"), "AuthType": "NONE"},
            },
            "UrlPermission": {
                "Type": "AWS::Lambda::Permission",
                "Properties": {"FunctionName": ref("QuotaFunction"), "Action": "lambda:InvokeFunctionUrl",
                               "Principal": "*", "FunctionUrlAuthType": "NONE"},
            },
            "FunctionPermission": {
                "Type": "AWS::Lambda::Permission",
                "Properties": {"FunctionName": ref("QuotaFunction"), "Action": "lambda:InvokeFunction",
                               "Principal": "*", "InvokedViaFunctionUrl": True},
            },
        },
        "Outputs": {"QuotaUrl": {"Value": {"Fn::GetAtt": ["QuotaUrl", "FunctionUrl"]}},
                    "TableName": {"Value": ref("BudgetTable")}},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    source = Path(__file__).with_name("handler.py").read_text()
    with options.output.open("x") as destination:
        json.dump(render_template(source), destination, indent=2)
        destination.write("\n")


if __name__ == "__main__":
    main()
