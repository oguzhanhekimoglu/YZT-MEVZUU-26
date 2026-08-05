import re

with open('entegrasyon/kokpit/Kokpit/MainWindow.xaml', 'r', encoding='utf-8') as f:
    content = f.read()

# First replace the Grid.RowDefinitions
row_def_old = """                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="*"/>
                </Grid.RowDefinitions>"""
row_def_new = """                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="*"/>
                </Grid.RowDefinitions>"""

content = content.replace(row_def_old, row_def_new)

# Now we find the VLM block inside VRAG and move it out
vlm_block_start = '<!-- İSTİHBARAT — VLM DENETİMİ (gemma VRAG\'ı denetler) -->'
vlm_block_end = '                        </StackPanel>\n                    </StackPanel>\n                </Border>\n\n                <!-- LLM -->'

vlm_pos_start = content.find(vlm_block_start)
vlm_pos_end = content.find('                    </StackPanel>\n                </Border>\n\n                <!-- LLM -->')

if vlm_pos_start != -1 and vlm_pos_end != -1:
    vlm_content = content[vlm_pos_start:vlm_pos_end]
    
    # We remove it from VRAG
    content = content[:vlm_pos_start] + content[vlm_pos_end:]
    
    # We wrap it in its own Border
    vlm_new_border = """
                <!-- VLM -->
                <Border Grid.Row="1" Margin="0,0,0,10" Background="{StaticResource Panel}" CornerRadius="10"
                        BorderBrush="{StaticResource Cizgi}" BorderThickness="1" Padding="14"
                        Visibility="{Binding SeciliHedef.VlmVar, Converter={StaticResource DusukGuvenGorunur}}">
                    <StackPanel>
                        <TextBlock Text="GÖRSEL İSTİHBARAT (VLM)" Style="{StaticResource Baslik}" Margin="2,0,0,10"/>
                        <WrapPanel Margin="0,0,0,6">
                            <Border CornerRadius="5" Padding="8,3" Margin="0,0,6,6" Background="{StaticResource PanelAcik}">
                                <TextBlock FontSize="12">
                                    <Run Text="tehdit: " Foreground="{StaticResource Solgun}"/><Run Text="{Binding SeciliHedef.Vlm.TehditSeviyesi}" FontWeight="SemiBold" Foreground="{StaticResource Tehdit}"/>
                                </TextBlock>
                            </Border>
                        </WrapPanel>
                        <TextBlock FontSize="12" Margin="0,0,0,4">
                            <Run Text="Sınıf: " Foreground="{StaticResource Solgun}"/><Run Text="{Binding SeciliHedef.Vlm.AracSinifi}" FontWeight="SemiBold"/>
                        </TextBlock>
                        <TextBlock Text="{Binding SeciliHedef.Vlm.GorselAnaliz}" TextWrapping="Wrap"
                                   FontSize="13" Foreground="{StaticResource Metin}" LineHeight="18"/>
                    </StackPanel>
                </Border>
"""
    
    # We insert it before LLM
    llm_pos = content.find('<!-- LLM -->')
    content = content[:llm_pos] + vlm_new_border + content[llm_pos:]
    
    # And we need to change Grid.Row="1" for LLM to Grid.Row="2"
    content = content.replace('<Border Grid.Row="1" Background="{StaticResource Panel}" CornerRadius="10"', 
                              '<Border Grid.Row="2" Background="{StaticResource Panel}" CornerRadius="10"')

    with open('entegrasyon/kokpit/Kokpit/MainWindow.xaml', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Done")
else:
    print("Could not find VLM block")
