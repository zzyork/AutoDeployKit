def confirm_yes_no(prompt_message, default=None, input_func=input, print_func=print):
    """
    获取用户选择确认

    Args:
        prompt_message (str): 提示信息
        default (bool|None): 默认选项
            - True  -> 回车默认 yes
            - False -> 回车默认 no
            - None  -> 必须输入 y/n
    Returns:
        bool
    """
    yes_set = {"y", "yes", "1", "true", "t", "是", "好", "确定"}
    no_set  = {"n", "no", "0", "false", "f", "否", "不", "取消"}

    # 构造提示 (Y/n) / (y/N) / (y/n)
    if default is True:
        suffix = " (Y/n): "
    elif default is False:
        suffix = " (y/N): "
    else:
        suffix = " (y/n): "

    while True:
        try:
            user_input = input_func(f"{prompt_message}{suffix}").strip().lower()
        except (KeyboardInterrupt, EOFError):
            # 中断时按默认值走；没默认就当作取消更安全
            return default if default is not None else False

        if user_input == "" and default is not None:
            return default

        if user_input in yes_set:
            return True
        if user_input in no_set:
            return False

        print_func("输入错误，请输入 y/n（或 yes/no）")


def menu_choice(
    prompt_message="请选择操作编号: ",
    valid_choices=None,
    default=None,
    allow_blank_as_default=True,
    input_func=input,
    print_func=print,
):
    choice_set = set(map(str, valid_choices)) if valid_choices is not None else None
    default_str = str(default) if default is not None else None

    while True:
        try:
            user_input = input_func(prompt_message)
        except (KeyboardInterrupt, EOFError):
            if default_str is not None:
                return default_str
            return ""

        user_input = user_input.strip()

        if user_input == "" and allow_blank_as_default and default_str is not None:
            return default_str

        if choice_set is None:
            if user_input:
                return user_input
        else:
            if user_input in choice_set:
                return user_input

        if choice_set is None:
            print_func("无效选项，请重新输入")
        else:
            print_func(f"无效选项，请重新输入（可选：{', '.join(sorted(choice_set))}）")
