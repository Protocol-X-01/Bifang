import json
import subprocess
from pathlib import Path


def template():
    return json.loads((Path(__file__).resolve().parents[1] / "deploy/aws/remote-host.json").read_text())


def test_host_has_no_public_app_or_ssh_ingress_and_no_credential_keys():
    resources = template()["Resources"]
    group = resources["HostSecurityGroup"]["Properties"]
    assert not group.get("SecurityGroupIngress")
    assert {rule["FromPort"] for rule in group["SecurityGroupEgress"]} == {80, 443}
    host = resources["Host"]["Properties"]
    assert "KeyName" not in host
    assert host["MetadataOptions"] == {"HttpTokens": "required", "HttpPutResponseHopLimit": 1}
    assert host["CreditSpecification"]["CPUCredits"] == "standard"
    assert host["BlockDeviceMappings"][0]["Ebs"]["Encrypted"]


def test_state_and_artifacts_are_private_encrypted_and_retained():
    resources = template()["Resources"]
    state = resources["StateVolume"]
    assert state["DeletionPolicy"] == state["UpdateReplacePolicy"] == "Retain"
    assert state["Properties"]["Encrypted"] and state["Properties"]["Size"] == 20
    bucket = resources["Artifacts"]
    assert bucket["DeletionPolicy"] == "Retain"
    assert all(bucket["Properties"]["PublicAccessBlockConfiguration"].values())
    assert bucket["Properties"]["BucketEncryption"]["ServerSideEncryptionConfiguration"][0]["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"
    tls = resources["ArtifactTlsPolicy"]["Properties"]["PolicyDocument"]["Statement"][0]
    assert tls["Effect"] == "Deny" and tls["Condition"]["Bool"]["aws:SecureTransport"] == "false"


def test_public_https_is_explicitly_opt_in_and_ip_is_stable():
    configuration = template()
    assert configuration["Parameters"]["EnableHttpsIngress"]["Default"] == "false"
    resources = configuration["Resources"]
    assert resources["StaticAddress"]["Properties"]["Domain"] == "vpc"
    assert resources["AddressAssociation"]["Properties"]["InstanceId"] == {"Ref": "Host"}
    assert resources["HttpsIngress"]["Condition"] == resources["AcmeIngress"]["Condition"] == "HttpsIngressEnabled"
    assert resources["HttpsIngress"]["Properties"]["FromPort"] == 443
    assert resources["AcmeIngress"]["Properties"]["FromPort"] == 80


def test_runtime_role_is_not_an_account_administrator():
    role = template()["Resources"]["HostRole"]["Properties"]
    assert not role.get("ManagedPolicyArns")
    statements = role["Policies"][0]["PolicyDocument"]["Statement"]
    actions = {action for statement in statements for action in
               (statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]])}
    assert "*" not in actions and not any(action.startswith(("iam:", "ec2:", "cloudformation:")) for action in actions)
    read = next(statement for statement in statements if statement["Action"] == "ssm:GetParameter")
    assert read["Resource"]["Fn::Sub"].endswith(":parameter/bifang/remote/*")
    artifact = next(statement for statement in statements if statement["Action"] == "s3:GetObject")
    assert artifact["Resource"]["Fn::Sub"] == "${Artifacts.Arn}/builds/*"


def test_bootstrap_shell_is_valid_and_contains_no_application_credentials(tmp_path):
    script = template()["Resources"]["Host"]["Properties"]["UserData"]["Fn::Base64"]["Fn::Sub"]
    assert "${StateVolume}" in script and "lsblk" in script
    assert "NEBIUS_API_KEY" not in script and "AWS_SECRET_ACCESS_KEY" not in script
    assert "10001" in script and "0700" in script
    target = tmp_path / "bootstrap.sh"
    target.write_text(script.replace("${StateVolume}", "vol-synthetic"))
    subprocess.run(["bash", "-n", str(target)], check=True, capture_output=True)
