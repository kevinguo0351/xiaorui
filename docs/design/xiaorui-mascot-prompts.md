# 小瑞角色素材与生成记录

使用内置 imagegen 工具生成，未调用公司 API，未指定或宣称“GPT Image 2.6”。官方型号检查见 https://developers.openai.com/api/reference/resources/images/methods/generate 。本轮确认的是当前内置工具可用，不能从工具结果推断实际服务型号。

项目使用的透明 PNG：

- `frontend/public/mascot/xiaorui-working.png`：举空白牌的小瑞，空白牌的实际状态文字由网页叠加；也用于闲置与头像。
- `frontend/public/mascot/xiaorui-taxi.png`：同一角色手持小出租车。
- `frontend/public/mascot/xiaorui-dining.png`：同一角色端着餐袋与汤碗。

下列为本轮最终提示词集；后两张以第一张为编辑参照，保持身份一致。原生成文件保留于本机 `.codex/generated_images/`；项目引用始终指向工作区素材，不依赖生成目录。

## 举牌角色

Use case: stylized-concept. Asset: original premium companion mascot cutout for a warm sophisticated Chinese elder-friendly personal assistant web app. Create ONE full-body small humanlike helper named Xiaorui, beautifully art-directed tactile paper-and-clay editorial illustration, not generic emoji, not glossy toy, not corporate clipart. Rounded warm ivory face with two tiny dark ink eyes, gentle subtle smile, peach blush, small warm terracotta knit cap, muted deep sage green overalls, cream shirt, tiny brown shoes. Compact friendly human proportions, oversized rounded head, little mitt hands. Standing three-quarter facing slightly right, holding a small clean BLANK ivory rectangular sign in both hands in front of chest with an olive rim, big enough to later overlay app text. Distinctive charming silhouette, quiet adult taste, high craft, warm natural soft studio light, subtle paper grain and clay texture, delicate minimal shadow directly beneath feet. Composition full body centered with comfortable generous transparent padding, no cropping, no environment, no background object. Color palette warm cream, muted sage, rust terracotta. NO letters, NO words, NO logos, NO badges. Real transparent alpha background.

## 打车形象

Edit this image into a consistent companion-mascot service illustration. Preserve EXACT same boy character face, terracotta knit hat, ivory shirt, muted sage overalls, paper-clay texture, soft light, scale, full-body cutout and transparent alpha. Change only pose and activity: Xiaorui is happily helping arrange a taxi, gently holding a tiny beautifully designed warm mustard-yellow taxi model at waist height in both hands instead of the blank board. Car has simple wheels and small blank roof sign, no lettering or logos. Slightly turned right with confident gentle smile, delicate shadow underneath. One character only, full body no cropping, no background or scene. Premium tactile editorial illustration. NO text, no letters.

## 点餐形象

Edit this image into a consistent companion-mascot service illustration. Preserve EXACT same boy character face, terracotta knit hat, ivory shirt, muted sage overalls, paper-clay texture, soft light, scale, full-body cutout and transparent alpha. Change only pose and activity: Xiaorui is helping order a meal, holding a small warm kraft-paper takeaway bag and a tiny cream soup bowl on a modest serving tray at waist height instead of the blank board. The bag has a simple tiny leaf mark, no branding, no lettering. Gentle friendly smile, delicate shadow underneath. One character only, full body no cropping, no background or scene. Premium tactile editorial illustration. NO text, no letters.

## 动态方式

动画由 CSS 循环和实际任务／语音状态驱动，未把 PNG 称为已经生成的 GIF。动态支持 `prefers-reduced-motion`。空闲、查询、打车、点餐、聆听与播报分别显示对应姿态／提示，不使用图片暗示查询、下单或付款已成功。未来可沿用角色扩充真正的逐帧 GIF／WebP 素材。
