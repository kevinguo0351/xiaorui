import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:xiaorui_mobile/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('companion page remains usable at narrow width and large text', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = 1.8;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const XiaoruiApp());
    await tester.pump();
    expect(find.text('小瑞'), findsOneWidget);
    expect(find.text('任务板'), findsOneWidget);
    expect(find.text('打字'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.tap(find.byTooltip('头像与设置'));
    await tester.pumpAndSettle();
    expect(find.text('支付方式'), findsOneWidget);
    await tester.tap(find.byType(SwitchListTile));
    await tester.pumpAndSettle();
    expect(find.text('按住说话'), findsOneWidget);
    expect((await SharedPreferences.getInstance()).getBool('hold'), isTrue);
    expect(find.text('尚未开通，仅展示'), findsNWidgets(2));
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
  });
}
