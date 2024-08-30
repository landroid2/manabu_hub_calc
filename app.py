import os
import sympy as sp
import time
import re
import numpy as np
import matplotlib.pyplot as plt
import uuid  # 追加
import threading
from flask import Flask, request, abort
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    ImageMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

app = Flask(__name__)

configuration = Configuration(access_token=os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

def add_spaces(expression):
    expression = re.sub(r'(?<=[^\s\+\-])(?=[\+\-])', ' ', expression)
    return expression

def add_multiplication_sign(expression):
    expression = re.sub(r'(?<=[\d])(?=[a-zA-Z])', '*', expression)  # 数字と変数の間
    expression = re.sub(r'(?<=[a-zA-Z])(?=[a-zA-Z])', '*', expression)  # 変数と変数の間
    expression = re.sub(r'(?<=[)])(?=[a-zA-Z])', '*', expression)  # 括弧と変数の間
    expression = re.sub(r'(?<=[\d])(?=[(])', '*', expression)  # 数字と括弧の間
    expression = re.sub(r'(?<=[a-zA-Z])(?=[(])', '*', expression)  # 変数と括弧の間
    expression = re.sub(r'(?<=[)])(?=[(])', '*', expression)  # 括弧と括弧の間
    return expression

def add_exponentiation_sign(expression):
    expression = str(expression).replace('^', '**') # ^を**に変換
    expression = re.sub(r'(?<=[a-zA-Z])(?=\d)', '**', expression)  # 文字と数字の間
    expression = re.sub(r'(?<=[)])(?=\d)', '**', expression)  # 括弧と数字の間
    return expression

def sort_expression(expression):
    expression = sp.sympify(expression)
    terms = expression.as_ordered_terms()
    sorted_terms = sorted(terms, key=lambda term: (sp.Poly(term).total_degree(), term.as_coefficients_dict().keys()))
    sorted_expr = sp.Add(*sorted_terms)
    return sorted_expr

def format_expression(expression):
    expanded_expr = sp.expand(sp.sympify(expression))  # 展開
    simplified_expr = sp.simplify(expanded_expr)  # 簡略化
    sorted_expr = sort_expression(simplified_expr)
    formatted_expr = str(sorted_expr).replace('**', '^').replace('*', '')
    return formatted_expr

def format_equation(left_expr, right_expr):
    left_minus_right_expr = left_expr - right_expr  # 左辺と右辺の差を簡略化
    formatted_expr = format_expression(left_minus_right_expr)
    return f"{formatted_expr} = 0"

def plot_graph(left_expr, right_expr, var1, var2):
    # 変数の範囲を設定
    x_vals = np.linspace(-10, 10, 400)  # xの範囲
    y_vals = np.linspace(-10, 10, 400)  # yの範囲
    X, Y = np.meshgrid(x_vals, y_vals)

    # タイトルを指定
    graph_title = format_equation(left_expr, right_expr)

    # 左辺と右辺の差を計算
    Z = sp.lambdify((var1, var2), left_expr - right_expr, 'numpy')(X, Y)  # Z = 0 になる部分を計算

    plt.figure(figsize=(8, 6))
    plt.contour(X, Y, Z, levels=[0], colors='blue')  # 等高線を描画
    plt.title(graph_title)
    plt.xlabel(var1)
    plt.ylabel(var2)
    plt.grid()
    plt.axhline(0, color='black', linewidth=0.5, ls='--')
    plt.axvline(0, color='black', linewidth=0.5, ls='--')

    # ランダムな文字列を生成して画像を保存
    random_string = uuid.uuid4().hex  # ランダムな文字列を生成
    image_path = os.path.join('static', f'graph_{random_string}.png')  # staticフォルダに保存
    plt.savefig(image_path)
    plt.close()

    # 画像ファイルの存在を確認
    if os.path.exists(image_path):
        print(f"画像ファイルが保存されました: {image_path}")
    else:
        print("画像ファイルの保存に失敗しました。")
    
    return image_path

def simplify_or_solve(expression):
    try:
        expression = add_spaces(expression)
        expression = add_multiplication_sign(expression)
        expression = add_exponentiation_sign(expression)

        equal_sign_count = expression.count('=')

        if equal_sign_count == 1:
            left_side, right_side = expression.split('=')
            left_expr = sp.sympify(left_side.strip())
            right_expr = sp.sympify(right_side.strip())

            # 変数の取得
            variables = list(left_expr.free_symbols.union(right_expr.free_symbols))
            eq = sp.Eq(left_expr - right_expr, 0)
            try:
                solutions = {var: sp.solve(eq, var) for var in variables}
                # 解の表示形式を調整
                result = ""
                for var, sols in sorted(solutions.items(), key=lambda x: str(x[0])):
                    if isinstance(sols, list):
                        for sol in sols:
                            sol = sort_expression(sol)
                            result += f"{var} = {sol}\n"
                    else:
                        result += f"{var} = {sols}\n"
                
                result_str = result.strip() if result else "解なし" # 解がない場合の処理
                result_str = str(result_str).replace('**', '^').replace('*', '')  # 形式を整形
                if len (variables) != 2:
                    return result_str
                else:
                    var1, var2 = sorted(variables, key=lambda v: str(v))  # アルファベット順でソート
                    image_path = plot_graph(left_expr, right_expr, str(var1), str(var2))  # グラフを描画
                    return result_str, image_path  # 画像パスを返す
            except Exception as e:
                print(f"エラー: {e}")
                return "解を求める際にエラーが発生しました。"

        elif equal_sign_count > 1:
            return "方程式には等号 (=) をちょうど1個含めてください！"
        else:
            expanded_expr = sp.expand(sp.sympify(expression))  # 展開
            simplified_expr = sp.simplify(expanded_expr)  # 簡略化
            simplified_expr_str = str(simplified_expr).replace('**', '^').replace('*', '')  # 形式を整形
            return f"{simplified_expr_str}"

    except (sp.SympifyError, TypeError) as e:
        print(f"SymPy error: {e}")
        return "数式を正しく入力してください！"


def delete_image_after_delay(image_path, delay=300):  # デフォルトは300秒（5分間）
    time.sleep(delay)
    if os.path.exists(image_path):
        os.remove(image_path)
        print(f"画像ファイルが削除されました: {image_path}")

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_message = event.message.text
    try:
        response = simplify_or_solve(user_message)
        if isinstance(response, tuple) and len(response) == 2:
            result_str, image_path = response
            image_path = response  # 画像パスを保存
            image_url = f"https://manabu-hub-calc.onrender.com/static/{os.path.basename(image_path)}"  # RenderのURLを指定
            
            line_bot_api = MessagingApi(ApiClient(configuration))
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[ImageMessage(original_content_url=image_url, preview_image_url=image_url)]
                )
            )
            print("画像送信応答:", image_path)

            # 画像送信後に別スレッドで削除処理を開始
            threading.Thread(target=delete_image_after_delay, args=(image_path,)).start()
        else:
            result_str = response
        # テキスト応答の場合
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=result_str)]
                )
            )
    except Exception as e:
        print(f"Error: {e}")
        response = "申し訳ございません。エラーが発生したようです。もう一度試しても正常に作動しなければ、お手数お掛けしますがまなぶHUBの公式LINEまでご連絡ください。"
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=response)]
                )
            )


if __name__ == "__main__":
    port = int(os.environ.get("PORT"))
    app.run(host='0.0.0.0', port=port)