import os
import sys

cur_path = os.path.abspath(os.path.dirname(__file__))
root_path = os.path.split(cur_path)[0]
sys.path.append(root_path)

import step1_extract
import step2_analyze
import step3_detect
import step4_verify_per_vulnerability
import step5_defense
import step7_chat
from temp_paths import get_temp_dir


def main(model="glm-5"):
    get_temp_dir()
    step1_extract.run_step_1(model)
    step2_analyze.run_step_2(model)
    # Step 3 currently performs a single forward-reasoning classification pass.
    # Keep its verifier implementation available, but do not invoke it in main.
    step3_detect.run_step_3(model, use_verifier=False)
    step4_verify_per_vulnerability.run_step_4(model)
    step5_defense.run_step_5()
    step7_chat.run_step_7()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--core-model", default="glm-5", dest="core_model")
    args = parser.parse_args()
    main(model=args.core_model)
